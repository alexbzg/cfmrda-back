#!/usr/bin/python3
#coding=utf-8
"""various constants and functions for working with ham radio data"""
import logging
import re
from rda import RDA_VALUES

BANDS_WL = {'160M': '1.8', '80M': '3.5', '40M': '7', \
        '30M': '10', '20M': '14', '14M': '20', '17M': '18', '15M': '21', \
        '12M': '24', '10M': '28', '6M': '50', '2M': '144', \
        '33CM': 'UHF', '23CM':'UHF', '13CM': 'UHF'}

BANDS = ("1.8", "3.5", "7", "10", "14", "18", "21", "24", "28")

MODES = {'DIGI': ('DATA', 'HELL', 'MT63', 'THOR16', 'FAX', 'OPERA', 'PKT', 'RY',\
                    'SIM31', 'CONTESTI', 'CONTESTIA', 'AMTOR', 'JT6M', 'ASCI',\
                    'FT8', 'MSK144', 'THOR', 'QRA64', 'DOMINO', 'JT4C', 'THROB',\
                    'DIG', 'ROS', 'SIM63', 'FSQ', 'THRB', 'J3E', 'WSPR', 'ISCAT',\
                    'JT65A', 'CONTESTIA8', 'ALE', 'JT10', 'TOR', 'PACKET', 'RTTY',\
                    'FSK63', 'MFSK63', 'QPSK63', 'PSK', 'JT65', 'FSK', 'OLIVIA',\
                    'CONTEST', 'SSTV', 'PSK31', 'PSK63', 'PSK125', 'JT9', 'FT8', \
                    'MFSK16', 'MFSK', 'ARDOP', 'ATV', 'C4FM', 'CHIP', 'CLO',\
                    'DIGITALVOICE', 'DOMINO', 'DSTAR', 'ISCAT', 'Q15', 'QPSK31',\
                    'QRA64', 'T10', 'THRB', 'VOI', 'WINMOR', 'WSPR', 'FT4', 'FT-8',\
                    'FT-4', 'QPSK125', 'BPSK63', 'BPSK125', 'BPSK'),\
         'CW': ('A1A'),\
         'SSB': ('USB', 'LSB', 'FM', 'AM', 'PHONE')}

RE_STRIP_CALLSIGN = re.compile(r"\d?[A-Z]+\d+[A-Z]+")

RE_RDA_VALUE = re.compile(r"([a-zA-Z][a-zA-Z])[\d-]*(\d\d)")

class Pfx():
    """class for determining prefix/country by callsign"""

    def __init__(self, cty_dat_path):
        re_country = re.compile(r"\s\*?(\S+):$")
        re_pfx = re.compile(r"(\(.*\))?(\[.*\])?")
        prefixes = [{}, {}]
        with open(cty_dat_path, 'r') as f_cty:
            for line in f_cty.readlines():
                line = line.rstrip('\r\n')
                m_country = re_country.search(line)
                if m_country:
                    country = m_country.group(1)
                else:
                    pfxs = line.lstrip(' ').rstrip(';,').split(',')
                    for pfx in pfxs:
                        pfx_type = 0
                        pfx0 = re_pfx.sub(pfx, "")
                        if pfx0.startswith("="):
                            pfx0 = pfx0.lstrip('=')
                            pfx_type = 1
                        if pfx0 in prefixes[pfx_type]:
                            prefixes[pfx_type][pfx0] += "; " + country
                        else:
                            prefixes[pfx_type][pfx0] = country
        self.prefixes = prefixes

    def get(self, callsign):
        """returns cs pfx"""
        dx_cty = None

        if callsign in self.prefixes[1]:
            dx_cty = self.prefixes[1][callsign]
        else:
            for cnt in range(1, len(callsign)):
                if callsign[:cnt] in self.prefixes[0]:
                    dx_cty = self.prefixes[0][callsign[:cnt]]

        return dx_cty

def detect_rda(val):
    """get valid rda value"""
    rda_match = RE_RDA_VALUE.search(val)
    if rda_match:
        rda = (rda_match.group(1) + '-' + rda_match.group(2)).upper()
        if rda in RDA_VALUES:
            return rda
    return None

def strip_callsign(callsign):
    """remove prefixes/suffixes from callsign"""
    cs_match = RE_STRIP_CALLSIGN.search(callsign)
    if cs_match:
        return cs_match.group(0)
    else:
        return None

def get_adif_field(line, field):
    """reads ADIF field"""
    i_head = line.find('<' + field + ':')
    if i_head < 0:
        return None
    i_beg = line.find(">", i_head) + 1
    ends = [x for x in [line.find(x, i_beg) for x in (' ', '<')] if x > -1]
    i_end = min(ends) if ends else len(line)
    return line[i_beg:i_end]

class ADIFParseException(Exception):
    """station_callsign_field is absent
    rda_field is absent
    no qso in file
    multiple activator callsigns
    """
    pass

def load_adif(adif, station_callsign_field=None, rda_field=None, ignore_activator=False):
    """parse adif data"""
    adif = adif.upper().replace('\r', '').replace('\n', '')
    data = {'qso': [], 'date_start': None, 'date_end': None,\
            'activator': None, 'message': '', 'qso_errors': {}, 
            'qso_errors_count': 0}
 
    def append_error(msg):
        if msg not in data['qso_errors']:
            data['qso_errors'][msg] = 0
        data['qso_errors'][msg] += 1
        data['qso_errors_count'] += 1
   
    if '<EOH>' in adif:
        adif = adif.split('<EOH>')[1]
    lines = adif.split('<EOR>')
    for line in lines:
        if '<' in line:
            qso = {}
            qso['callsign'] = get_adif_field(line, 'CALL')
            qso['mode'] = get_adif_field(line, 'MODE')
            qso['band'] = get_adif_field(line, 'BAND')

            if qso['band']:
                qso['band'] = qso['band'].replace(',', '.')
                if qso['band'] in BANDS_WL:
                    qso['band'] = BANDS_WL[qso['band']]
            if qso['band'] not in BANDS:
                append_error('Поле не найдено или некорректно (BAND)')
                continue

            if qso['callsign']:
                qso['callsign'] = strip_callsign(qso['callsign'])
            if not qso['callsign']:
                append_error('Поле не найдено или некорректно (CALLSIGN)')
                continue

            if not qso['mode']:
                append_error('Поле не найдено или некорректно (MODE)')
                continue
            if qso['mode'] not in MODES:
                for mode in MODES:
                    if qso['mode'] in MODES[mode]:
                        qso['mode'] = mode
                        break
            if qso['mode'] not in MODES:
                append_error('Некорректная мода. Invalid mode. (' + str(qso['mode']) +')')
                continue

            qso_date = get_adif_field(line, 'QSO_DATE')
            qso_time = get_adif_field(line, 'TIME_ON')
            if not qso_date:
                append_error('Поле не найдено или некорректно (QSO_DATE)')
                continue
            if not qso_time:
                append_error('Поле не найдено или некорректно (TIME_ON)')
                continue
            qso['tstamp'] = qso_date + ' ' + qso_time

            if station_callsign_field:
                qso['station_callsign'] = \
                    get_adif_field(line, station_callsign_field)
                if not qso['station_callsign']:
                    data['qso_errors'] += 1
                    continue
                if not ignore_activator:
                    activator = strip_callsign(qso['station_callsign'])
                    if not activator:
                        data['qso_errors'] += 1
                        continue
                    if data['activator']:
                        if data['activator'] != activator:
                            raise ADIFParseException(\
                                "Различные активаторы в одном файле (" +\
                                data['activator'] + ', ' + activator + ")")
                    else:
                        data['activator'] = activator

            if rda_field:
                qso['rda'] = None
                rda = get_adif_field(line, rda_field)
                if rda:
                    qso['rda'] = detect_rda(rda)
                else:
                    append_error('Поле не найдено или некорректно ('\
                        + rda_field.upper() + ')')
                    continue
                if not qso['rda']:
                    logging.debug('Invalid RDA: ' + str(rda))
                    append_error('Некорректное значение RDA (' + str(rda) + ')')
                    continue

            if not data['date_start'] or data['date_start'] > qso['tstamp']:
                data['date_start'] = qso['tstamp']
            if not data['date_end'] or data['date_end'] < qso['tstamp']:
                data['date_end'] = qso['tstamp']

            data['qso'].append(qso)

    if not data['qso']:
        data['message'] = "Не найдено корректных qso" + \
            (' ' + data['message'] if data['message'] else '')

    return data
