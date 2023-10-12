import uuid

from aiohttp import web

from cfmrda.json_utils import load_json, save_json
from cfmrda.web_responses import response_ok, response_error_unauthorized

def get_announce_index(announces, callsign, ann_id):
    for i, announce in enumerate(announces):
        if ann_id == announce['id']:
            assert announce['user'] == callsign
            return i
    return -1

class AnnouncesService():

    def __init__(self, conf):
        self.__file_path = conf.get('web', 'root') + '/json/ann.json'

    def __read_file(self):
        return load_json(self.__file_path()) or []

    def __write_file(self, data):
        save_json(data, self.__file_path())

    async def post_hndlr(self, callsign, data):
        anns = self.__read_file()
        data['announce']['id'] = uuid.uuid1()
        data['announce']['user'] = callsign
        anns.insert(0, data['announce'])
        self.__write_file(anns)
        return response_ok()

    async def put_hndlr(self, callsign, data):
        anns = self.__read_file()
        try:
            edit_index = get_announce_index(anns, callsign, data['announce']['id'])
        except AssertionError:
            return response_error_unauthorized()
        if edit_index == -1:
            return web.HTTPNotFound()
        anns[edit_index] = data['announce']
        self.__write_file(anns)
        return response_ok()

    async def del_hndlr(self, callsign, data):
        anns = self.__read_file()
        try:
            edit_index = get_announce_index(anns, callsign, data['announce_id'])
        except AssertionError:
            return response_error_unauthorized()
        if edit_index == -1:
            return web.HTTPNotFound()
        del anns[edit_index]
        self.__write_file(anns)
        return response_ok()
