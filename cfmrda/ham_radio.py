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
                    'QRA64', 'T10', 'THRB', 'VOI', 'WINMOR', 'WSPR')
         'CW': ('A1A'),\
         'SSB': ('USB', 'LSB', 'FM', 'AM', 'PHONE')}

RE_STRIP_CALLSIGN = re.compile(r"\d?[A-Z]+\d+[A-Z]+")

RE_RDA_VALUE = re.compile(r"([a-zA-Z][a-zA-Z])[\d-]*(\d\d)")

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

def load_adif(adif, station_callsign_field=None, rda_field=None):
    """parse adif data"""
    adif = adif.upper().replace('\r', '').replace('\n', '')
    data = {'qso': [], 'date_start': None, 'date_end': None,\
            'activator': None, 'message': '', 'qso_errors': 0}
    missing_fields = set([])
    invalid_rda = set([])
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
                missing_fields.add('band')
                continue

            if qso['callsign']:
                qso['callsign'] = strip_callsign(qso['callsign'])
            if not qso['callsign']:
                missing_fields.add('callsign')
                data['qso_errors'] += 1
                continue

            if not qso['mode']:
                missing_fields.add('mode')
                data['qso_errors'] += 1
                continue
            if qso['mode'] not in MODES:
                for mode in MODES:
                    if qso['mode'] in MODES[mode]:
                        qso['mode'] = mode
                        break
            if qso['mode'] not in MODES:
                missing_fields.add('mode')
                data['qso_errors'] += 1
                continue

            qso_date = get_adif_field(line, 'QSO_DATE')
            qso_time = get_adif_field(line, 'TIME_ON')
            if not qso_date:
                missing_fields.add('qso_date')
                data['qso_errors'] += 1
                continue
            if not qso_time:
                missing_fields.add('time_on')
                data['qso_errors'] += 1
                continue
            qso['tstamp'] = qso_date + ' ' + qso_time

            if station_callsign_field:
                qso['station_callsign'] = \
                    get_adif_field(line, station_callsign_field)
                if not qso['station_callsign']:
                    data['qso_errors'] += 1
                    continue
                activator = strip_callsign(qso['station_callsign'])
                if not activator:
                    data['qso_errors'] += 1
                    continue
                if data['activator']:
                    if data['activator'] != activator:
                        raise ADIFParseException(\
                            "Различные активаторы в одном файле: " +\
                            data['activator'] + ', ' + activator)
                else:
                    data['activator'] = activator

            if rda_field:
                qso['rda'] = None
                rda = get_adif_field(line, rda_field)
                if rda:
                    qso['rda'] = detect_rda(rda)
                if not qso['rda']:
                    logging.debug('Invalid RDA: ' + str(rda))
                    invalid_rda.add(rda)
                    data['qso_errors'] += 1
                    continue

            if not data['date_start'] or data['date_start'] > qso['tstamp']:
                data['date_start'] = qso['tstamp']
            if not data['date_end'] or data['date_end'] < qso['tstamp']:
                data['date_end'] = qso['tstamp']

            data['qso'].append(qso)

    if missing_fields:
        data['message'] += "\nНе найдены или некорректно заполнены поля: " + ', '.join(missing_fields)
    if invalid_rda:
        data['message'] += "\nНекорректные RDA: " + ', '.join(invalid_rda)

    if not data['qso']:
        data['message'] = "Не найдено корректных qso." + \
            (' ' + data['message'] if data['message'] else '')
        raise ADIFParseException(data['message'])

    return data
