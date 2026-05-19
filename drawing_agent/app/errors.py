ASYNC_GENERATOR_ACLOSE_ERROR = "aclose(): asynchronous generator is already running"


def is_async_generator_aclose_error(exc: BaseException) -> bool:
    return isinstance(exc, RuntimeError) and ASYNC_GENERATOR_ACLOSE_ERROR in str(exc)
