#
# Copyright 2010 Nick Foster
# 
# This file is part of gr-air-modes
# 
# gr-air-modes is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# gr-air-modes is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with gr-air-modes; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
# 

import time, os, sys, threading
from string import split, join
import modes_parse
import sqlite3
from modes_exceptions import *

class modes_output_sql(modes_parse.modes_parse):
  def __init__(self, mypos, filename):
    modes_parse.modes_parse.__init__(self, mypos)

    self._lock = threading.Lock()
    #create the database
    self.db = sqlite3.connect(filename)
    #now execute a schema to create the tables you need
    c = self.db.cursor()
    query = """CREATE TABLE IF NOT EXISTS "positions" (
                "icao" INTEGER KEY NOT NULL,
                "seen" TEXT NOT NULL,
                "alt"  INTEGER,
                "lat"  REAL,
                "lon"  REAL
            );"""
    self.locked_execute(c, query)
    query = """CREATE TABLE IF NOT EXISTS "vectors" (
                "icao"     INTEGER KEY NOT NULL,
                "seen"     TEXT NOT NULL,
                "speed"    REAL,
                "heading"  REAL,
                "vertical" REAL
            );"""
    self.locked_execute(c, query)
    query = """CREATE TABLE IF NOT EXISTS "ident" (
                "icao"     INTEGER PRIMARY KEY NOT NULL,
                "ident"    TEXT NOT NULL
            );"""
    self.locked_execute(c, query)
    c.close()
    self.db.commit()

  def __del__(self):
    self.db.close()

  def locked_execute(self, c, query):
    with self._lock:
      c.execute(query)

  def output(self, message):
    try:
      query = self.make_insert_query(message)
      if query is not None:
        with self._lock:
          c = self.db.cursor()
          c.execute(query)
          c.close()
          self.db.commit()
    except ADSBError:
      pass

  def make_insert_query(self, message):
    #assembles a SQL query tailored to our database
    #this version ignores anything that isn't Type 17 for now, because we just don't care
    [data, ecc, reference, timestamp] = message.split()

    data = modes_parse.modes_reply(long(data, 16))
    ecc = long(ecc, 16)
#   reference = float(reference)


    query = None
    msgtype = data["df"]
    if msgtype == 17:
      query = self.sql17(data)

    return query

  def sql17(self, data):
    icao24 = data["aa"]
    bdsreg = data["me"].get_type()

    retstr = None

    if bdsreg == 0x08:
      (msg, typename) = self.parseBDS08(data)
      retstr = "INSERT OR REPLACE INTO ident (icao, ident) VALUES (" + "%i" % icao24 + ", '" + msg + "')"

    elif bdsreg == 0x06:
      [ground_track, decoded_lat, decoded_lon, rnge, bearing] = self.parseBDS06(data)
      altitude = 0
      if decoded_lat is None: #no unambiguously valid position available
        retstr = None
      else:
        retstr = "INSERT INTO positions (icao, seen, alt, lat, lon) VALUES (" + "%i" % icao24 + ", datetime('now'), " + str(altitude) + ", " + "%.6f" % decoded_lat + ", " + "%.6f" % decoded_lon + ")"

    elif bdsreg == 0x05:
      [altitude, decoded_lat, decoded_lon, rnge, bearing] = self.parseBDS05(data)
      if decoded_lat is None: #no unambiguously valid position available
        retstr = None
      else:
        retstr = "INSERT INTO positions (icao, seen, alt, lat, lon) VALUES (" + "%i" % icao24 + ", datetime('now'), " + str(altitude) + ", " + "%.6f" % decoded_lat + ", " + "%.6f" % decoded_lon + ")"

    elif bdsreg == 0x09:
      subtype = data["bds09"].get_type()
      if subtype == 0:
        [velocity, heading, vert_spd, turnrate] = self.parseBDS09_0(data)
        retstr = "INSERT INTO vectors (icao, seen, speed, heading, vertical) VALUES (" + "%i" % icao24 + ", datetime('now'), " + "%.0f" % velocity + ", " + "%.0f" % heading + ", " + "%.0f" % vert_spd + ")"
      elif subtype == 1:
        [velocity, heading, vert_spd] = self.parseBDS09_1(data)  
        retstr = "INSERT INTO vectors (icao, seen, speed, heading, vertical) VALUES (" + "%i" % icao24 + ", datetime('now'), " + "%.0f" % velocity + ", " + "%.0f" % heading + ", " + "%.0f" % vert_spd + ")"
      else:
        retstr = None
        
    return retstr
