import uuid

from aiohttp import web

from cfmrda.utils.json_utils import load_json, save_json
from cfmrda.utils.web_responses import response_ok, response_error_unauthorized

def get_announce_index(announces, callsign, ann_id):
    for i, announce in enumerate(announces):
        if ann_id == announce['id']:
            if announce['user'] == callsign:
                return i
            raise response_error_unauthorized()
    raise web.HTTPNotFound()

class AnnouncesService():

    def __init__(self, conf):
        self.__file_path = conf.get('web', 'root') + '/json/ann.json'

    def __read_file(self):
        return load_json(self.__file_path()) or []

    def __write_file(self, data):
        save_json(data, self.__file_path())

    def get_announce_for_edit(self, callsign, ann_id):
        anns = self.__read_file()
        for i, announce in enumerate(announces):
            if ann_id == announce['id']:
                if announce['user'] == callsign:
                    return (anns, i)
                raise response_error_unauthorized()
        raise web.HTTPNotFound()

    async def create(self, callsign, data):
        anns = self.__read_file()
        data['announce']['id'] = uuid.uuid1()
        data['announce']['user'] = callsign
        anns.insert(0, data['announce'])
        self.__write_file(anns)
        return response_ok()

    async def update(self, callsign, data):
        anns, edit_index = self.get_announce_for_edit(callsign, data['announce']['id'])
        anns[edit_index] = data['announce']
        self.__write_file(anns)
        return response_ok()

    async def delete(self, callsign, data):
        anns, edit_index = self.get_announce_for_edit(callsign, data['id'])
        del anns[edit_index]
        self.__write_file(anns)
        return response_ok()
