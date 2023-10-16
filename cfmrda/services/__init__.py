from cfmrda.common import CONF

from cfmrda.services.auth import AuthService
auth_service = AuthService(CONF)

from cfmrda.services.announces import AnnouncesService
announces_service = AnnouncesService(CONF)
