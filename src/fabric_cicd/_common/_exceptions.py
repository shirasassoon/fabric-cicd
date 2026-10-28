# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Custom exceptions for the fabric-cicd package."""

from logging import Logger
from typing import Optional


def _format_error_details(label: str, error: Exception) -> str:
    """Format an exception section with optional request details."""
    details = f"\n--- {label} ---\n{error}"
    additional_info = getattr(error, "additional_info", None)
    if additional_info:
        details += f"\n{additional_info}"
    return details


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
        additional_info = "\n".join(_format_error_details(context, error) for context, error in self.errors)
        super().__init__(f"Cleanup failed: {details}", logger, additional_info)


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
        cleanup_only = bool(self.cleanup_errors) and not errors and operation_error is None
        if operation_error is not None:
            message = f"Publish operation failed: {operation_error}"
        elif cleanup_only:
            message = "Publishing succeeded, but cleanup failed"
        else:
            failed_names = [name for name, _ in errors]
            message = f"Failed to publish {len(errors)} item(s): {failed_names}"

        if self.cleanup_errors:
            cleanup_details = "; ".join(f"{item_type}: {exc}" for item_type, exc in self.cleanup_errors)
            prefix = ": " if cleanup_only else ". Cleanup also failed: "
            message += prefix + cleanup_details
        if post_publish_error is not None:
            message += f". The post-publish step also failed: {post_publish_error}"

        additional_info_parts = []
        for item_name, exc in errors:
            additional_info_parts.append(f"\n--- {item_name} ---\n{exc!s}")
        if operation_error is not None:
            additional_info_parts.append(_format_error_details("publish operation", operation_error))
        for item_type, exc in self.cleanup_errors:
            additional_info_parts.append(_format_error_details(f"cleanup ({item_type})", exc))
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
