class AuthService():

    def __init__(self, conf):
        self.__admins = set(str(conf.get('web', 'admins')).split(' '))

    def is_admin(self, callsign):
        return callsign in self.__admins
