class LinkitinError(Exception):
    pass


class AuthError(LinkitinError):
    pass


class RateLimitError(LinkitinError):
    pass


class PostError(LinkitinError):
    pass


class MediaError(LinkitinError):
    pass


class SessionError(LinkitinError):
    pass
