//! Rayon 线程池配置。
//!
//! 本模块负责读取 Rust 原生核心线程数配置，并在需要时使用局部线程池执行并发任务。

use std::env;

#[cfg(test)]
thread_local! {
    static THREAD_COUNT_OVERRIDE: std::cell::RefCell<Option<String>> =
        const { std::cell::RefCell::new(None) };
}

pub(crate) fn run_with_optional_pool<F, R>(job: F) -> Result<R, String>
where
    F: FnOnce() -> R + Send,
    R: Send,
{
    #[cfg(test)]
    let thread_count = read_configured_thread_count_for_test()?;
    #[cfg(not(test))]
    let thread_count = read_configured_thread_count()?;

    if let Some(thread_count) = thread_count {
        let pool = match rayon::ThreadPoolBuilder::new()
            .num_threads(thread_count)
            .build()
        {
            Ok(pool) => pool,
            Err(error) => return Err(format!("Rust 线程池创建失败: {error}")),
        };
        return Ok(pool.install(job));
    }
    Ok(job())
}

#[cfg(test)]
fn read_configured_thread_count_for_test() -> Result<Option<usize>, String> {
    let override_value = THREAD_COUNT_OVERRIDE.with(|value| value.borrow().clone());
    if let Some(raw_value) = override_value {
        return parse_configured_thread_count(&raw_value);
    }
    read_configured_thread_count()
}

#[cfg(test)]
pub(crate) fn with_thread_count_override_for_test<F, R>(raw_value: Option<&str>, job: F) -> R
where
    F: FnOnce() -> R,
{
    let previous_value =
        THREAD_COUNT_OVERRIDE.with(|value| value.replace(raw_value.map(str::to_owned)));
    let _guard = ThreadCountOverrideGuard { previous_value };

    job()
}

#[cfg(test)]
struct ThreadCountOverrideGuard {
    previous_value: Option<String>,
}

#[cfg(test)]
impl Drop for ThreadCountOverrideGuard {
    fn drop(&mut self) {
        THREAD_COUNT_OVERRIDE.with(|value| value.replace(self.previous_value.take()));
    }
}

pub(crate) fn read_configured_thread_count() -> Result<Option<usize>, String> {
    let raw_value = match env::var("ATT_MZ_RUST_THREADS") {
        Ok(value) => value,
        Err(env::VarError::NotPresent) => return Ok(None),
        Err(error) => return Err(format!("读取 ATT_MZ_RUST_THREADS 失败: {error}")),
    };
    parse_configured_thread_count(&raw_value)
}

pub(crate) fn parse_configured_thread_count(raw_value: &str) -> Result<Option<usize>, String> {
    let normalized_value = raw_value.trim();
    let parsed = normalized_value.parse::<usize>().map_err(|error| {
        format!("ATT_MZ_RUST_THREADS 必须是非负整数: {normalized_value}: {error}")
    })?;
    if parsed == 0 {
        return Ok(None);
    }
    Ok(Some(parsed))
}

#[cfg(test)]
mod tests {
    use super::parse_configured_thread_count;

    #[test]
    fn thread_count_env_value_controls_configured_pool_size() {
        assert_eq!(parse_configured_thread_count("4"), Ok(Some(4)));
        assert_eq!(parse_configured_thread_count("64"), Ok(Some(64)));
        assert_eq!(parse_configured_thread_count(" 2 "), Ok(Some(2)));
        assert_eq!(parse_configured_thread_count("0"), Ok(None));
        assert!(parse_configured_thread_count("invalid").is_err());
    }
}
