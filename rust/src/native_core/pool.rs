//! Rayon 线程池配置。
//!
//! 本模块负责读取 Rust 原生核心线程数配置，并在需要时使用局部线程池执行并发任务。

use std::sync::RwLock;

static CONFIGURED_THREAD_COUNT: RwLock<Option<usize>> = RwLock::new(None);

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

pub(crate) fn configure_runtime_threads(thread_count: Option<usize>) -> Result<(), String> {
    if matches!(thread_count, Some(0)) {
        return Err("runtime.rust_threads 必须是正整数或 auto".to_owned());
    }
    let mut configured_thread_count = CONFIGURED_THREAD_COUNT
        .write()
        .map_err(|error| format!("Rust 线程配置锁已损坏: {error}"))?;
    *configured_thread_count = thread_count;
    Ok(())
}

pub(crate) fn read_configured_thread_count() -> Result<Option<usize>, String> {
    let configured_thread_count = CONFIGURED_THREAD_COUNT
        .read()
        .map_err(|error| format!("Rust 线程配置锁已损坏: {error}"))?;
    Ok(*configured_thread_count)
}

#[cfg(test)]
pub(crate) fn parse_configured_thread_count(raw_value: &str) -> Result<Option<usize>, String> {
    let normalized_value = raw_value.trim();
    if normalized_value == "auto" {
        return Ok(None);
    }
    let parsed = normalized_value.parse::<usize>().map_err(|error| {
        format!("runtime.rust_threads 必须是正整数或 auto: {normalized_value}: {error}")
    })?;
    if parsed == 0 {
        return Err("runtime.rust_threads 必须是正整数或 auto".to_owned());
    }
    Ok(Some(parsed))
}

#[cfg(test)]
mod tests {
    use super::{configure_runtime_threads, read_configured_thread_count};

    #[test]
    fn runtime_thread_config_accepts_auto_or_positive_count() {
        configure_runtime_threads(Some(4)).expect("正整数线程数应可配置");
        assert_eq!(read_configured_thread_count(), Ok(Some(4)));

        configure_runtime_threads(None).expect("auto 应清除线程数覆盖");
        assert_eq!(read_configured_thread_count(), Ok(None));

        let error = configure_runtime_threads(Some(0)).expect_err("0 不是有效线程数");
        assert!(error.contains("runtime.rust_threads 必须是正整数或 auto"));
    }
}
