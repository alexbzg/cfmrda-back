#!/usr/bin/python3
#coding=utf-8
"""various constants and functions for working with ham radio data"""
#import logging

BANDS_WL = {'160M': '1.8', '80M': '3.5', '40M': '7', \
        '30M': '10', '20M': '14', '14M': '20', '17M': '18', '15M': '21', \
        '12M': '24', '10M': '28', '6M': '50', '2M': '144', \
        '33CM': 'UHF', '23CM':'UHF', '13CM': 'UHF'}

BANDS = ("1.8", "3.5", "7", "10", "14", "18", "21", "24", "28")

def get_adif_field(line, field):
    i_head = line.find('<' + field + ':')
    if i_head < 0:
        return None
    i_beg = line.find(">", i_head) + 1
    ends = [x for x in [line.find(x, i_beg) for x in (' ', '<')] if x > -1]
    i_end = min(ends) if ends else len(line)
    return line[i_beg:i_end]

class ADIFParseException(Exception):
    """currently only when station_callsign_field is absent or no qso in file"""
    pass

def load_adif(adif, station_callsign_field=None):
    adif = adif.upper().replace('\r', '').replace('\n', '')
    data = {'qso': [], 'date_start': None, 'date_end': None}
    if '<EOH>' in adif:
        adif = adif.split('<EOH>')[1]
    lines = adif.split('<EOR>')
    for line in lines:
        if '<' in line:
            qso = {}
            qso['callsign'] = get_adif_field(line, 'CALL')
            qso['mode'] = get_adif_field(line, 'MODE')
            qso['band'] = get_adif_field(line, 'BAND')
            if not qso['band']:
                continue
            qso['band'] = qso['band'].replace(',', '.')
            if qso['band'] in BANDS_WL:
                qso['band'] = BANDS_WL[qso['band']]
            if qso['band'] not in BANDS or not qso['callsign']:
                continue

            qso['tstamp'] = get_adif_field(line, 'QSO_DATE') + ' ' + \
                    get_adif_field(line, 'TIME_ON')

            if station_callsign_field:
                qso['station_callsign'] = \
                    get_adif_field(line, station_callsign_field)
                if not qso['station_callsign']:
                    raise ADIFParseException(\
                        "Не найдено поле позывного активатора ('" + \
                        station_callsign_field + "').")

            if not data['date_start'] or data['date_start'] > qso['tstamp']:
                data['date_start'] = qso['tstamp']
            if not data['date_end'] or data['date_end'] < qso['tstamp']:
                data['date_end'] = qso['tstamp']

            data['qso'].append(qso)
    if data['qso']:
        return data
    else:
        raise ADIFParseException("Не найдено корректных qso.")
