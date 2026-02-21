class LinkitError(Exception):
    pass


class AuthError(LinkitError):
    pass


class RateLimitError(LinkitError):
    pass


class PostError(LinkitError):
    pass


class MediaError(LinkitError):
    pass


class SessionError(LinkitError):
    pass
