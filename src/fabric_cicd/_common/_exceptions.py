# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Custom exceptions for the fabric-cicd package."""

from logging import Logger
from typing import Optional


class BaseCustomError(Exception):
    def __init__(self, message: str, logger: Logger, additional_info: Optional[str] = None) -> None:
        """
        Initialize the BaseCustomError.

        Args:
            message: The error message.
            logger: The logger instance.
            additional_info: Additional information about the error.
        """
        super().__init__(message)
        self.logger = logger
        self.additional_info = additional_info


class ParsingError(BaseCustomError):
    pass


class InputError(BaseCustomError):
    pass


class TokenError(BaseCustomError):
    pass


class InvokeError(BaseCustomError):
    pass


class ItemDependencyError(BaseCustomError):
    pass


class FileTypeError(BaseCustomError):
    pass


class ParameterFileError(BaseCustomError):
    pass


class FailedPublishedItemStatusError(BaseCustomError):
    pass


class CleanupError(BaseCustomError):
    """Retain every cleanup failure with its resource context and request details."""

    def __init__(self, errors: list[tuple[str, Exception]], logger: Logger) -> None:
        """Initialize with resource descriptions and their original exceptions."""
        self.errors = list(errors)
        details = "; ".join(f"{context}: {error}" for context, error in self.errors)
        additional_info_parts = []
        for context, error in self.errors:
            error_info = f"\n--- {context} ---\n{error}"
            request_info = getattr(error, "additional_info", None)
            if request_info:
                error_info += f"\n{request_info}"
            additional_info_parts.append(error_info)
        super().__init__(f"Cleanup failed: {details}", logger, "\n".join(additional_info_parts))


class PublishError(BaseCustomError):
    """Exception raised when one or more publish operations fail.

    Attributes:
        errors: List of (item_name, exception) tuples for all failed items.
        post_publish_error: The error raised by post_publish_all(), if it also failed.
        cleanup_errors: List of (item_type, exception) tuples for failed lifecycle cleanup.
        operation_error: An earlier setup or bulk-operation error when individual item failures are unavailable.
    """

    def __init__(
        self,
        errors: list[tuple[str, Exception]],
        logger: Logger,
        post_publish_error: Optional[Exception] = None,
        *,
        cleanup_errors: Optional[list[tuple[str, Exception]]] = None,
        operation_error: Optional[Exception] = None,
    ) -> None:
        """Retain the primary failure and any cleanup or post-publish failures."""
        self.errors = errors
        self.post_publish_error = post_publish_error
        self.cleanup_errors = list(cleanup_errors) if cleanup_errors is not None else []
        self.operation_error = operation_error
        failed_names = [name for name, _ in errors]
        message = (
            f"Publish operation failed: {operation_error}"
            if operation_error is not None
            else f"Failed to publish {len(errors)} item(s): {failed_names}"
        )
        cleanup_only = bool(self.cleanup_errors) and not errors and operation_error is None
        if cleanup_only:
            message = "Publishing succeeded, but cleanup failed"
        if self.cleanup_errors:
            cleanup_details = "; ".join(f"{item_type}: {exc}" for item_type, exc in self.cleanup_errors)
            message += f": {cleanup_details}" if cleanup_only else f". Cleanup also failed: {cleanup_details}"
        if post_publish_error is not None:
            message += f". The post-publish step also failed: {post_publish_error}"

        additional_info_parts = []
        for item_name, exc in errors:
            additional_info_parts.append(f"\n--- {item_name} ---\n{exc!s}")
        if operation_error is not None:
            operation_info = getattr(operation_error, "additional_info", None)
            additional_info_parts.append(f"\n--- publish operation ---\n{operation_error!s}")
            if operation_info:
                additional_info_parts.append(operation_info)
        for item_type, exc in self.cleanup_errors:
            cleanup_info = f"\n--- cleanup ({item_type}) ---\n{exc!s}"
            request_info = getattr(exc, "additional_info", None)
            if request_info:
                cleanup_info += f"\n{request_info}"
            additional_info_parts.append(cleanup_info)
        post_publish_info = getattr(post_publish_error, "additional_info", None)
        if post_publish_info:
            additional_info_parts.append(f"\n--- post_publish_all ---\n{post_publish_info}")
        additional_info = "\n".join(additional_info_parts) if additional_info_parts else None

        super().__init__(message, logger, additional_info)

    @classmethod
    def from_operation_error(
        cls, error: Exception, cleanup_errors: list[tuple[str, Exception]], logger: Logger
    ) -> "PublishError":
        """Combine lifecycle cleanup failures without losing an existing publish error's details."""
        if isinstance(error, cls):
            return cls(
                error.errors,
                logger,
                error.post_publish_error,
                cleanup_errors=error.cleanup_errors + cleanup_errors,
                operation_error=error.operation_error,
            )
        return cls([], logger, cleanup_errors=cleanup_errors, operation_error=error)
