"""插件源码文本定位工具。"""


def plugin_source_file_key(file_name: str) -> str:
    """返回统一文本范围中的插件源码文件键。"""
    return f"js/plugins/{file_name}"


def plugin_source_location_path(*, file_name: str, selector: str) -> str:
    """返回插件源码文本内部定位键。"""
    return f"{plugin_source_file_key(file_name)}/{selector}"


def parse_plugin_source_location_path(location_path: str) -> tuple[str, str] | None:
    """从内部定位键解析插件源码文件名和 selector。"""
    prefix = "js/plugins/"
    if not location_path.startswith(prefix):
        return None
    remain = location_path[len(prefix):]
    parts = remain.split("/", 1)
    if len(parts) != 2:
        return None
    file_name, selector = parts
    if not file_name.endswith(".js") or not selector:
        return None
    return file_name, selector


__all__ = [
    "parse_plugin_source_location_path",
    "plugin_source_file_key",
    "plugin_source_location_path",
]
