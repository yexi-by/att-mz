"""多游戏数据库管理模块。"""

from pathlib import Path
from dataclasses import dataclass
from types import TracebackType
from typing import Self, cast, override

import aiosqlite

from app.language import DEFAULT_TARGET_LANGUAGE, SourceLanguage, TargetLanguage, parse_source_language
from app.rmmz.schema import (
    EngineKind,
    GameData,
    GameLayout,
)
from app.rmmz.loader import read_game_title, resolve_game_directory, resolve_game_layout
from app.observability.logging import logger

from .font_records import FontRecordSessionMixin
from .rows import row_str
from .paths import DB_DIRECTORY, build_db_path, ensure_db_directory, resolve_default_db_directory
from .records import GameMetadata, GameRecord, LanguageSettings, RuleReviewStateRecord
from .rule_records import RuleRecordSessionMixin
from .run_records import RunRecordSessionMixin
from .session_utils import build_event_command_group_key, current_timestamp_text
from .sql import (
    CHECK_CONNECTION_READABLE,
    CREATE_SCHEMA_VERSION_TABLE,
    CREATE_EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE,
    CREATE_EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE,
    CREATE_EVENT_COMMAND_TEXT_RULE_PATHS_TABLE,
    CREATE_FONT_REPLACEMENT_RECORDS_TABLE,
    CREATE_LANGUAGE_SETTINGS_TABLE,
    CREATE_LLM_FAILURES_TABLE,
    CREATE_METADATA_TABLE,
    CREATE_MV_VIRTUAL_NAMEBOX_RULES_TABLE,
    CREATE_NOTE_TAG_TEXT_RULES_TABLE,
    CREATE_PLACEHOLDER_RULES_TABLE,
    CREATE_PLUGIN_TEXT_RULES_TABLE,
    CREATE_PLUGIN_SOURCE_TEXT_RULES_TABLE,
    CREATE_RULE_REVIEW_STATES_TABLE,
    CREATE_SOURCE_RESIDUAL_RULES_TABLE,
    CREATE_STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE,
    CREATE_STRUCTURED_PLACEHOLDER_RULES_TABLE,
    CREATE_TRANSLATION_QUALITY_ERRORS_TABLE,
    CREATE_TRANSLATION_RUNS_TABLE,
    CREATE_TRANSLATION_TABLE,
    CREATE_TERMINOLOGY_BUNDLE_STATE_TABLE,
    CREATE_TEXT_GLOSSARY_TERMS_TABLE,
    CREATE_FIELD_TRANSLATION_TERMS_TABLE,
    CURRENT_SCHEMA_VERSION,
    EXPECTED_STATIC_TABLE_NAMES,
    LANGUAGE_SETTINGS_KEY,
    METADATA_KEY,
    SCHEMA_VERSION_KEY,
    SELECT_LANGUAGE_SETTINGS,
    SELECT_METADATA,
    SELECT_SCHEMA_VERSION,
    SELECT_TABLE_NAMES,
    UPSERT_LANGUAGE_SETTINGS,
    UPSERT_METADATA,
    UPSERT_SCHEMA_VERSION,
)
from .terminology_records import TerminologyRecordSessionMixin
from .translation_records import TranslationRecordSessionMixin

type ColumnSchemaSignature = tuple[int, str, str, int, str | None, int]
type ForeignKeySchemaSignature = tuple[int, int, str, str, str, str, str, str]
type IndexSchemaSignature = tuple[int, str, int, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class TableSchemaSignature:
    """单张 SQLite 表的当前结构签名。"""

    columns: tuple[ColumnSchemaSignature, ...]
    foreign_keys: tuple[ForeignKeySchemaSignature, ...]
    indexes: tuple[IndexSchemaSignature, ...]


type DatabaseSchemaSignature = dict[str, TableSchemaSignature]

async def open_connection(db_path: Path) -> aiosqlite.Connection:
    """打开 SQLite 连接并设置统一行工厂。"""
    connection = await aiosqlite.connect(db_path)
    connection.row_factory = aiosqlite.Row
    _ = await connection.execute("PRAGMA foreign_keys = ON")
    return connection


async def check_connection_readable(connection: aiosqlite.Connection, db_path: Path) -> None:
    """对已打开连接执行最轻量可读性检查。"""
    async with connection.execute(CHECK_CONNECTION_READABLE) as cursor:
        row = await cursor.fetchone()

    if row is None:
        raise RuntimeError(f"数据库可读性校验失败，未返回任何结果: {db_path}")
    if row[0] != 1:
        raise RuntimeError(f"数据库可读性校验失败，返回值异常: {db_path}")


async def read_table_names(connection: aiosqlite.Connection) -> set[str]:
    """读取当前 SQLite 文件中的全部表名。"""
    async with connection.execute(SELECT_TABLE_NAMES) as cursor:
        rows = await cursor.fetchall()
    table_names: set[str] = set()
    for row in rows:
        table_name = cast(object, row["name"])
        if not isinstance(table_name, str):
            raise RuntimeError("数据库表名读取结果不是字符串")
        table_names.add(table_name)
    return table_names


def _schema_mismatch_error(db_path: Path, detail: str) -> RuntimeError:
    """构造当前数据库结构校验失败信息。"""
    return RuntimeError(
        f"数据库结构不符合当前版本，请删除对应游戏数据库后重新注册游戏，再重新导入规则和译名: {db_path}；{detail}"
    )


async def ensure_schema_compatible(connection: aiosqlite.Connection, db_path: Path) -> None:
    """确认已有数据库完整匹配当前 schema。"""
    table_names = await read_table_names(connection)
    expected_table_names = set(EXPECTED_STATIC_TABLE_NAMES)
    internal_table_names = {"sqlite_sequence"}
    missing_table_names = sorted(expected_table_names - table_names)
    unexpected_table_names = sorted(table_names - expected_table_names - internal_table_names)
    if missing_table_names:
        raise _schema_mismatch_error(db_path, f"缺少表 {', '.join(missing_table_names)}")
    if unexpected_table_names:
        raise _schema_mismatch_error(db_path, f"存在未声明表 {', '.join(unexpected_table_names)}")

    expected_schema = await build_current_schema_signature()
    actual_schema = await read_database_schema_signature(
        connection=connection,
        table_names=EXPECTED_STATIC_TABLE_NAMES,
    )
    mismatched_schema_tables = [
        table_name
        for table_name in EXPECTED_STATIC_TABLE_NAMES
        if actual_schema.get(table_name) != expected_schema.get(table_name)
    ]
    if mismatched_schema_tables:
        raise _schema_mismatch_error(db_path, f"表结构不匹配 {', '.join(mismatched_schema_tables)}")

    try:
        async with connection.execute(SELECT_SCHEMA_VERSION, (SCHEMA_VERSION_KEY,)) as cursor:
            row = await cursor.fetchone()
    except aiosqlite.Error as error:
        raise _schema_mismatch_error(db_path, "schema_version 不可读取") from error
    if row is None or row[0] != CURRENT_SCHEMA_VERSION:
        raise _schema_mismatch_error(db_path, "schema_version 不是当前版本")


async def build_current_schema_signature() -> DatabaseSchemaSignature:
    """用当前建表 SQL 生成标准数据库结构签名。"""
    connection = await aiosqlite.connect(":memory:")
    connection.row_factory = aiosqlite.Row
    try:
        _ = await connection.execute("PRAGMA foreign_keys = ON")
        await create_static_tables(connection)
        return await read_database_schema_signature(
            connection=connection,
            table_names=EXPECTED_STATIC_TABLE_NAMES,
        )
    finally:
        await connection.close()


async def read_database_schema_signature(
    *,
    connection: aiosqlite.Connection,
    table_names: tuple[str, ...],
) -> DatabaseSchemaSignature:
    """读取指定表集合的列、外键和索引结构签名。"""
    schema: DatabaseSchemaSignature = {}
    for table_name in table_names:
        schema[table_name] = TableSchemaSignature(
            columns=await read_table_column_schema(connection=connection, table_name=table_name),
            foreign_keys=await read_table_foreign_key_schema(connection=connection, table_name=table_name),
            indexes=await read_table_index_schema(connection=connection, table_name=table_name),
        )
    return schema


async def read_table_column_schema(
    *,
    connection: aiosqlite.Connection,
    table_name: str,
) -> tuple[ColumnSchemaSignature, ...]:
    """读取单表列定义签名。"""
    async with connection.execute(f"PRAGMA table_info([{table_name}])") as cursor:
        rows = await cursor.fetchall()
    return tuple(
        (
            row_int_value(row, "cid"),
            row_text_value(row, "name"),
            row_text_value(row, "type"),
            row_int_value(row, "notnull"),
            row_optional_text_value(row, "dflt_value"),
            row_int_value(row, "pk"),
        )
        for row in rows
    )


async def read_table_foreign_key_schema(
    *,
    connection: aiosqlite.Connection,
    table_name: str,
) -> tuple[ForeignKeySchemaSignature, ...]:
    """读取单表外键定义签名。"""
    async with connection.execute(f"PRAGMA foreign_key_list([{table_name}])") as cursor:
        rows = await cursor.fetchall()
    return tuple(
        (
            row_int_value(row, "id"),
            row_int_value(row, "seq"),
            row_text_value(row, "table"),
            row_text_value(row, "from"),
            row_text_value(row, "to"),
            row_text_value(row, "on_update"),
            row_text_value(row, "on_delete"),
            row_text_value(row, "match"),
        )
        for row in rows
    )


async def read_table_index_schema(
    *,
    connection: aiosqlite.Connection,
    table_name: str,
) -> tuple[IndexSchemaSignature, ...]:
    """读取单表唯一索引和主键索引签名。"""
    async with connection.execute(f"PRAGMA index_list([{table_name}])") as cursor:
        rows = await cursor.fetchall()
    signatures: list[IndexSchemaSignature] = []
    for row in rows:
        index_name = row_text_value(row, "name")
        columns = await read_index_column_names(connection=connection, index_name=index_name)
        signatures.append(
            (
                row_int_value(row, "unique"),
                row_text_value(row, "origin"),
                row_int_value(row, "partial"),
                columns,
            )
        )
    return tuple(sorted(signatures))


async def read_index_column_names(
    *,
    connection: aiosqlite.Connection,
    index_name: str,
) -> tuple[str, ...]:
    """读取索引覆盖的列名。"""
    async with connection.execute(f"PRAGMA index_info([{index_name}])") as cursor:
        rows = await cursor.fetchall()
    return tuple(row_text_value(row, "name") for row in rows)


def row_text_value(row: aiosqlite.Row, key: str) -> str:
    """从 SQLite 行读取字符串字段。"""
    value = cast(object, row[key])
    if not isinstance(value, str):
        raise RuntimeError(f"数据库结构字段不是字符串: {key}")
    return value


def row_optional_text_value(row: aiosqlite.Row, key: str) -> str | None:
    """从 SQLite 行读取可空字符串字段。"""
    value = cast(object, row[key])
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"数据库结构字段不是字符串或空值: {key}")
    return value


def row_int_value(row: aiosqlite.Row, key: str) -> int:
    """从 SQLite 行读取整数字段。"""
    value = cast(object, row[key])
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"数据库结构字段不是整数: {key}")
    return value


async def create_static_tables(connection: aiosqlite.Connection) -> None:
    """初始化当前数据库要求的全部静态表。"""
    _ = await connection.execute(CREATE_SCHEMA_VERSION_TABLE)
    _ = await connection.execute(CREATE_TRANSLATION_TABLE)
    _ = await connection.execute(CREATE_METADATA_TABLE)
    _ = await connection.execute(CREATE_LANGUAGE_SETTINGS_TABLE)
    _ = await connection.execute(CREATE_PLUGIN_TEXT_RULES_TABLE)
    _ = await connection.execute(CREATE_PLUGIN_SOURCE_TEXT_RULES_TABLE)
    _ = await connection.execute(CREATE_NOTE_TAG_TEXT_RULES_TABLE)
    _ = await connection.execute(CREATE_EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE)
    _ = await connection.execute(CREATE_EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE)
    _ = await connection.execute(CREATE_EVENT_COMMAND_TEXT_RULE_PATHS_TABLE)
    _ = await connection.execute(CREATE_FIELD_TRANSLATION_TERMS_TABLE)
    _ = await connection.execute(CREATE_TEXT_GLOSSARY_TERMS_TABLE)
    _ = await connection.execute(CREATE_TERMINOLOGY_BUNDLE_STATE_TABLE)
    _ = await connection.execute(CREATE_PLACEHOLDER_RULES_TABLE)
    _ = await connection.execute(CREATE_STRUCTURED_PLACEHOLDER_RULES_TABLE)
    _ = await connection.execute(CREATE_STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE)
    _ = await connection.execute(CREATE_SOURCE_RESIDUAL_RULES_TABLE)
    _ = await connection.execute(CREATE_MV_VIRTUAL_NAMEBOX_RULES_TABLE)
    _ = await connection.execute(CREATE_RULE_REVIEW_STATES_TABLE)
    _ = await connection.execute(CREATE_FONT_REPLACEMENT_RECORDS_TABLE)
    _ = await connection.execute(CREATE_TRANSLATION_RUNS_TABLE)
    _ = await connection.execute(CREATE_LLM_FAILURES_TABLE)
    _ = await connection.execute(CREATE_TRANSLATION_QUALITY_ERRORS_TABLE)
    _ = await connection.execute(
        UPSERT_SCHEMA_VERSION,
        (SCHEMA_VERSION_KEY, CURRENT_SCHEMA_VERSION),
    )
    await connection.commit()


async def write_metadata(
    connection: aiosqlite.Connection,
    game_title: str,
    game_path: Path,
    layout: GameLayout,
) -> None:
    """把游戏标题与游戏根目录写入元数据表。"""
    _ = await connection.execute(
        UPSERT_METADATA,
        (
            METADATA_KEY,
            game_title,
            str(game_path),
            layout.engine_kind,
            str(layout.content_root),
            layout.engine_version,
        ),
    )
    await connection.commit()


async def write_language_settings(
    connection: aiosqlite.Connection,
    source_language: SourceLanguage,
    target_language: TargetLanguage = DEFAULT_TARGET_LANGUAGE,
) -> None:
    """保存当前游戏的源语言和目标语言设置。"""
    _ = await connection.execute(
        UPSERT_LANGUAGE_SETTINGS,
        (
            LANGUAGE_SETTINGS_KEY,
            source_language,
            target_language,
        ),
    )
    await connection.commit()


async def read_metadata(connection: aiosqlite.Connection, db_path: Path) -> GameMetadata:
    """从元数据表恢复游戏标题和游戏根目录。"""
    try:
        async with connection.execute(SELECT_METADATA, (METADATA_KEY,)) as cursor:
            row = await cursor.fetchone()
    except aiosqlite.Error as error:
        raise RuntimeError(
            f"数据库 metadata 缺少 MV/MZ 引擎字段或表结构不可读，请重新注册游戏: {db_path}"
        ) from error

    if row is None:
        raise RuntimeError(f"数据库缺少 metadata 元数据记录: {db_path}")

    game_title = row_str(row, "game_title", db_path)
    game_path = row_str(row, "game_path", db_path)
    engine_kind_text = row_str(row, "engine_kind", db_path)
    content_root = row_str(row, "content_root", db_path)
    engine_version = row_str(row, "engine_version", db_path)
    if not game_title.strip():
        raise RuntimeError(f"metadata.game_title 非法: {db_path}")
    if not game_path.strip():
        raise RuntimeError(f"metadata.game_path 非法: {db_path}")
    if engine_kind_text not in {"mv", "mz"}:
        raise RuntimeError(f"metadata.engine_kind 非法，请重新注册游戏: {db_path}")
    engine_kind: EngineKind = "mv" if engine_kind_text == "mv" else "mz"
    if not content_root.strip():
        raise RuntimeError(f"metadata.content_root 非法，请重新注册游戏: {db_path}")
    if not engine_version.strip():
        raise RuntimeError(f"metadata.engine_version 非法，请重新注册游戏: {db_path}")
    return GameMetadata(
        game_title=game_title.strip(),
        game_path=Path(game_path).resolve(),
        engine_kind=engine_kind,
        content_root=Path(content_root).resolve(),
        engine_version=engine_version.strip(),
    )


async def read_language_settings(connection: aiosqlite.Connection, db_path: Path) -> LanguageSettings:
    """读取当前游戏语言设置；缺失时要求重新注册游戏。"""
    try:
        async with connection.execute(SELECT_LANGUAGE_SETTINGS, (LANGUAGE_SETTINGS_KEY,)) as cursor:
            row = await cursor.fetchone()
    except aiosqlite.Error as error:
        raise RuntimeError(
            f"数据库语言设置表不可读取，请重新注册游戏: {db_path}"
        ) from error
    if row is None:
        raise RuntimeError(
            f"数据库缺少语言设置记录，请重新注册游戏: {db_path}"
        )
    source_language = parse_source_language(row_str(row, "source_language", db_path))
    target_language = row_str(row, "target_language", db_path).strip()
    if target_language != DEFAULT_TARGET_LANGUAGE:
        raise RuntimeError(f"数据库 target_language 非法: {db_path}")
    return LanguageSettings(source_language=source_language, target_language=DEFAULT_TARGET_LANGUAGE)


class GameRegistry:
    """游戏注册表，负责发现、注册和打开目标游戏数据库。"""

    def __init__(self, db_directory: Path | None = None) -> None:
        """初始化注册表。"""
        self.db_directory: Path = db_directory if db_directory is not None else resolve_default_db_directory()

    async def list_games(self) -> list[GameRecord]:
        """扫描数据库目录并读取每个数据库的元数据。"""
        _ = ensure_db_directory(self.db_directory)
        records: list[GameRecord] = []
        for db_path in sorted(self.db_directory.glob("*.db")):
            connection = await open_connection(db_path)
            try:
                await check_connection_readable(connection=connection, db_path=db_path)
                await ensure_schema_compatible(connection=connection, db_path=db_path)
                metadata = await read_metadata(connection=connection, db_path=db_path)
                language_settings = await read_language_settings(connection=connection, db_path=db_path)
                records.append(
                    GameRecord(
                        game_title=metadata.game_title,
                        game_path=metadata.game_path,
                        db_path=db_path,
                        engine_kind=metadata.engine_kind,
                        content_root=metadata.content_root,
                        engine_version=metadata.engine_version,
                        source_language=language_settings.source_language,
                        target_language=language_settings.target_language,
                    )
                )
            finally:
                await connection.close()
        return sorted(records, key=lambda record: record.game_title)

    async def register_game(
        self,
        game_path: str | Path,
        source_language: SourceLanguage,
    ) -> GameRecord:
        """创建或更新单个游戏数据库绑定。"""
        _ = ensure_db_directory(self.db_directory)
        resolved_game_path = resolve_game_directory(game_path)
        layout = resolve_game_layout(resolved_game_path)
        game_title = read_game_title(resolved_game_path)
        db_path = build_db_path(game_title, self.db_directory)
        db_already_exists = db_path.exists()
        connection = await open_connection(db_path)
        previous_game_path: Path | None = None
        try:
            if db_already_exists:
                await check_connection_readable(connection=connection, db_path=db_path)
                await ensure_schema_compatible(connection=connection, db_path=db_path)
                previous_metadata = await read_metadata(
                    connection=connection,
                    db_path=db_path,
                )
                previous_game_title = previous_metadata.game_title
                previous_game_path = previous_metadata.game_path
                if previous_game_title != game_title:
                    raise RuntimeError(
                        f"数据库元数据标题与文件名目标不一致: {db_path}"
                    )
            if not db_already_exists:
                await create_static_tables(connection)
            await write_metadata(connection, game_title, resolved_game_path, layout)
            await write_language_settings(connection, source_language)
        except Exception:
            await connection.close()
            if not db_already_exists and db_path.exists():
                db_path.unlink(missing_ok=True)
            raise

        await connection.close()
        if previous_game_path is not None and previous_game_path != resolved_game_path:
            logger.warning(
                f"[tag.warning]检测到同标题游戏路径变化，已更新数据库绑定路径[/tag.warning] 标题 [tag.count]{game_title}[/tag.count] 新路径 [tag.path]{resolved_game_path}[/tag.path]"
            )
        return GameRecord(
            game_title=game_title,
            game_path=resolved_game_path,
            db_path=db_path,
            engine_kind=layout.engine_kind,
            content_root=layout.content_root,
            engine_version=layout.engine_version,
            source_language=source_language,
            target_language=DEFAULT_TARGET_LANGUAGE,
        )

    async def open_game(self, game_title: str) -> "TargetGameSession":
        """打开目标游戏数据库，返回命令级会话。"""
        _ = ensure_db_directory(self.db_directory)
        db_path = build_db_path(game_title, self.db_directory)
        if not db_path.exists():
            raise ValueError(f"未找到游戏数据库: {game_title}")

        connection = await open_connection(db_path)
        try:
            await check_connection_readable(connection=connection, db_path=db_path)
            await ensure_schema_compatible(connection=connection, db_path=db_path)
            metadata = await read_metadata(
                connection=connection,
                db_path=db_path,
            )
            language_settings = await read_language_settings(connection=connection, db_path=db_path)
            if metadata.game_title != game_title:
                raise RuntimeError(
                    f"数据库元数据标题不匹配: 期望 {game_title}，实际 {metadata.game_title}"
                )
            return TargetGameSession(
                record=GameRecord(
                    game_title=metadata.game_title,
                    game_path=metadata.game_path,
                    db_path=db_path,
                    engine_kind=metadata.engine_kind,
                    content_root=metadata.content_root,
                    engine_version=metadata.engine_version,
                    source_language=language_settings.source_language,
                    target_language=language_settings.target_language,
                ),
                connection=connection,
            )
        except Exception:
            await connection.close()
            raise

    async def resolve_registered_title_by_path(self, game_path: str | Path) -> str:
        """根据已注册游戏目录解析数据库中的游戏标题。"""
        resolved_game_path = resolve_game_directory(game_path)
        for record in await self.list_games():
            if record.game_path == resolved_game_path:
                return record.game_title
        title = read_game_title(resolved_game_path)
        raise ValueError(f"游戏目录尚未注册，请先执行 add-game: {title}")


class TargetGameSession(
    TranslationRecordSessionMixin,
    RuleRecordSessionMixin,
    TerminologyRecordSessionMixin,
    FontRecordSessionMixin,
    RunRecordSessionMixin,
):
    """单个目标游戏的数据库会话。"""

    def __init__(self, record: GameRecord, connection: aiosqlite.Connection) -> None:
        """初始化单游戏数据库会话。"""
        self.record: GameRecord = record
        self.connection: aiosqlite.Connection = connection
        self.game_data: GameData | None = None

    @property
    def game_title(self) -> str:
        """返回当前会话绑定的游戏标题。"""
        return self.record.game_title

    @property
    def game_path(self) -> Path:
        """返回当前会话绑定的游戏目录。"""
        return self.record.game_path

    @property
    @override
    def db_path(self) -> Path:
        """返回当前会话绑定的数据库路径。"""
        return self.record.db_path

    @property
    def engine_kind(self) -> EngineKind:
        """返回当前游戏注册时识别到的引擎类型。"""
        return self.record.engine_kind

    @property
    def content_root(self) -> Path:
        """返回当前游戏真实内容目录。"""
        return self.record.content_root

    @property
    def engine_version(self) -> str:
        """返回当前游戏注册时识别到的引擎版本。"""
        return self.record.engine_version

    @property
    def source_language(self) -> SourceLanguage:
        """返回当前游戏注册时选择的源语言。"""
        return self.record.source_language

    @property
    def target_language(self) -> TargetLanguage:
        """返回当前游戏固定目标语言。"""
        return self.record.target_language

    async def __aenter__(self) -> Self:
        """进入命令级数据库会话。"""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出命令级数据库会话并关闭连接。"""
        await self.close()

    def set_game_data(self, game_data: GameData) -> None:
        """把当前命令已加载的游戏数据绑定到会话。"""
        self.game_data = game_data

    def require_game_data(self) -> GameData:
        """读取当前会话已加载的游戏数据。"""
        if self.game_data is None:
            raise RuntimeError("当前命令尚未加载游戏数据")
        return self.game_data


    async def close(self) -> None:
        """关闭当前游戏数据库连接。"""
        await self.connection.close()


__all__: list[str] = [
    "DB_DIRECTORY",
    "GameMetadata",
    "GameRecord",
    "GameRegistry",
    "LanguageSettings",
    "RuleReviewStateRecord",
    "TargetGameSession",
    "build_event_command_group_key",
    "build_db_path",
    "current_timestamp_text",
    "ensure_db_directory",
    "resolve_default_db_directory",
]
