#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''
visa_identify
Giovanni Sartorello (srtgnn@gmail.com)
Look for VISA devices whose addresses or IDN strings match given inputs.
Version 1
Python 3.7.2
Created 2019-Feb-28
'''
from re import findall
import visa

class visa_identify():

    def __init__(self):
        '''Initialize a pyVISA resource manger.'''
        self.rm = visa.ResourceManager()

    def address(self, addrStr):
        '''Return all VISA addresses which match the input "addrStr".'''
        resources = self.rm.list_resources()
        matches = []
        for x in range(0, len(resources)):
            if findall(addrStr, resources[x]):
                matches.append(resources[x])
        return matches

    def identify(self, *idnStr):
        '''With no inputs, return all VISA addresses. With one input string,
        return the addresses which match that string. With two input strings,
        return the addresses which match the first and whose IDN string matches
        the second.'''
        resources = self.rm.list_resources()
        if not idnStr: # no inputs: behaves as rm.list_resources()
            identified = resources
        elif len(idnStr) == 1: # behaves as self.address()
            identified = self.address(idnStr[0])
        elif len(idnStr) == 2: # searches both address and IDN string
            addressed = self.address(idnStr[0])
            identified = []
            for x in range(0, len(addressed)):
                try:
                    instrument = self.rm.open_resource(addressed[x])
                    idn = instrument.query('*IDN?')
                    instrument.close()
                    if findall(idnStr[1], idn):
                        identified.append(addressed[x])
                except:
                    print('Failed to communicate with %s.' % addressed[x])
        else:
            print(('Incorrect query: use no inputs, one string to match'
                'addresses, or two to match address and IDN string.'))
        return identified
