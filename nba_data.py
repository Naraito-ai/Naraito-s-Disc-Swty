# -*- coding: utf-8 -*-
"""
Shared NBA 2K Mobile Catalog Data, Formulas, Themes, Graphics Generator and Lookup Helpers
"""
from __future__ import annotations
import os
import io
import re
import math
import time
import ssl
import json
import random
import logging
import unicodedata
import urllib.request
from collections import OrderedDict
from typing import Optional, Union, List, Dict, Any, Tuple, Set

import discord
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

from database import db

logger = logging.getLogger('sweety_bot.nba_data')

def is_creator(user: Union[discord.User, discord.Member, int]) -> bool:
    uid = user if isinstance(user, int) else getattr(user, 'id', 0)
    return uid == 719932313919684670 or str(uid) == '719932313919684670'


import gc
import sys

def clean_memory():
    """Aggressively runs Python garbage collection and trims glibc heap memory on Linux to stay well under Render 512MB limit."""
    try:
        gc.collect()
        if sys.platform.startswith("linux"):
            try:
                import ctypes
                libc = ctypes.CDLL("libc.so.6")
                if hasattr(libc, "malloc_trim"):
                    libc.malloc_trim(0)
            except Exception:
                pass
    except Exception:
        pass


class LRUImageCache:
    """Bounded in-memory image cache with max capacity to prevent RAM exhaustion."""
    def __init__(self, max_size: int = 20):
        self.max_size = max_size
        self._cache: OrderedDict[str, Image.Image] = OrderedDict()

    def get(self, key: str) -> Optional[Image.Image]:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, img: Image.Image):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.max_size:
                old_k, old_img = self._cache.popitem(last=False)
                try:
                    old_img.close()
                except Exception:
                    pass
            self._cache[key] = img

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def __getitem__(self, key: str) -> Image.Image:
        return self._cache[key]

    def __setitem__(self, key: str, img: Image.Image):
        self.set(key, img)

NBA_2K_TIERS = { 'amethyst': { 'color': 11225020,
                'desc': 'All-Star playmakers and top scoring threats.',
                'emoji': '🔮',
                'name': 'Amethyst',
                'ovr_range': '88-92',
                'quick_sell': 500,
                'short_name': 'Amethyst'},
  'dark_matter': { 'color': 8069026,
                   'desc': 'The most elite, unguardable superstars in basketball history.',
                   'emoji': '🌌',
                   'name': 'Dark Matter / G.O.A.T.',
                   'ovr_range': '99',
                   'quick_sell': 8000,
                   'short_name': 'Dark Matter'},
  'diamond': { 'color': 2718207,
               'desc': 'Elite franchise cornerstones and legendary champions.',
               'emoji': '💎',
               'name': 'Pink Diamond / Diamond',
               'ovr_range': '93-96',
               'quick_sell': 1200,
               'short_name': 'Diamond'},
  'exclusive': { 'color': 16716947,
                 'desc': 'Ultra-rare, unpullable masterpiece cards celebrating legendary iconic moments.',
                 'emoji': '👑',
                 'name': 'Exclusive / Immortal',
                 'ovr_range': '90-99',
                 'quick_sell': 100000,
                 'short_name': 'Exclusive'},
  'galaxy_opal': { 'color': 58879,
                   'desc': 'Pinnacle all-NBA talent with game-breaking signature moves.',
                   'emoji': '✨',
                   'name': 'Galaxy Opal',
                   'ovr_range': '97-98',
                   'quick_sell': 3000,
                   'short_name': 'Galaxy Opal'},
  'gold': { 'color': 16766720,
            'desc': 'Key rotation sparkplugs and clutch role players.',
            'emoji': '🟡',
            'name': 'Gold / Emerald',
            'ovr_range': '75-83',
            'quick_sell': 50,
            'short_name': 'Gold'},
  'ruby': { 'color': 15022389,
            'desc': 'High-impact starters and defensive specialists.',
            'emoji': '🔴',
            'name': 'Ruby',
            'ovr_range': '84-87',
            'quick_sell': 200,
            'short_name': 'Ruby'}}

NBA_2K_CARD_THEMES = { 'amethyst': { 'bg_bot': (55, 18, 90),
                'bg_top': (25, 12, 45),
                'border': (233, 213, 255),
                'glow': (168, 85, 247),
                'name': 'AMETHYST',
                'primary': (192, 132, 252),
                'secondary': (147, 51, 234)},
  'dark_matter': { 'bg_bot': (48, 16, 78),
                   'bg_top': (18, 10, 35),
                   'border': (216, 180, 254),
                   'glow': (192, 132, 252),
                   'name': 'DARK MATTER',
                   'primary': (168, 85, 247),
                   'secondary': (236, 72, 153)},
  'diamond': { 'bg_bot': (14, 55, 95),
               'bg_top': (8, 28, 50),
               'border': (224, 242, 254),
               'glow': (125, 211, 252),
               'name': 'DIAMOND',
               'primary': (56, 189, 248),
               'secondary': (186, 230, 253)},
  'exclusive': { 'bg_bot': (50, 10, 65),
                 'bg_top': (20, 5, 28),
                 'border': (255, 215, 0),
                 'glow': (255, 105, 180),
                 'name': 'EXCLUSIVE EDITION',
                 'primary': (255, 20, 147),
                 'secondary': (255, 215, 0)},
  'galaxy_opal': { 'bg_bot': (35, 15, 60),
                   'bg_top': (10, 25, 45),
                   'border': (165, 243, 252),
                   'glow': (103, 232, 249),
                   'name': 'GALAXY OPAL',
                   'primary': (6, 182, 212),
                   'secondary': (244, 114, 182)},
  'gold': { 'bg_bot': (85, 58, 12),
            'bg_top': (38, 26, 8),
            'border': (254, 240, 138),
            'glow': (251, 191, 36),
            'name': 'GOLD',
            'primary': (245, 158, 11),
            'secondary': (253, 230, 138)},
  'ruby': { 'bg_bot': (80, 15, 25),
            'bg_top': (40, 10, 15),
            'border': (254, 202, 202),
            'glow': (248, 113, 113),
            'name': 'RUBY',
            'primary': (239, 68, 68),
            'secondary': (251, 113, 133)}}

PLAYER_NICKNAMES = { 'Aaron Gordon': ['gordon', 'ag'],
  'Alex Caruso': ['caruso', 'bald mamba', 'carushow'],
  'Allen Iverson': ['iverson', 'ai', 'the answer'],
  'Anthony Davis': ['ad', 'davis', 'the brow'],
  'Anthony Edwards': ['ant', 'ant-man', 'ant man', 'edwards'],
  'Austin Reaves': ['reaves', 'ar15'],
  'Bam Adebayo': ['bam', 'adebayo'],
  'Bobby Portis': ['portis', 'bobby'],
  'Brandin Podziemski': ['podziemski', 'podz'],
  'Cam Thomas': ['cam thomas', 'thomas'],
  'Chet Holmgren': ['chet', 'holmgren'],
  'Coby White': ['coby'],
  'Damian Lillard': ['dame', 'lillard', 'dame dolla'],
  "De'Aaron Fox": ['fox', 'swipa'],
  'Dereck Lively II': ['lively', 'dereck lively'],
  'Derrick White': ['derrick', 'dwhite'],
  'Devin Booker': ['booker', 'book', 'dbook'],
  'Dirk Nowitzki': ['dirk', 'nowitzki'],
  'Domantas Sabonis': ['sabonis'],
  'Donovan Mitchell': ['mitchell', 'spida'],
  'Franz Wagner': ['franz', 'wagner'],
  'Giannis Antetokounmpo': ['giannis', 'antetokounmpo', 'greek freak'],
  'Hakeem Olajuwon': ['hakeem', 'the dream', 'olajuwon'],
  'Herb Jones': ['herb', 'herb jones'],
  'Ja Morant': ['ja', 'morant'],
  'Jaime Jaquez Jr.': ['jaime', 'jaquez', 'jaquez jr'],
  'Jalen Brunson': ['brunson', 'jalen'],
  'Jalen Green': ['jalen green'],
  'Jamal Murray': ['murray'],
  'Jaylen Brown': ['jaylen', 'jb'],
  'Jayson Tatum': ['tatum', 'jt'],
  'Jimmy Butler': ['butler', 'playoff jimmy', 'jimmy buckets'],
  'Joel Embiid': ['embiid', 'the process'],
  'Jrue Holiday': ['jrue', 'holiday'],
  'Karl-Anthony Towns': ['kat', 'towns'],
  'Kawhi Leonard': ['kawhi', 'the claw', 'the klaw'],
  'Kevin Durant': ['kd', 'durant', 'slim reaper'],
  'Kobe Bryant': ['kobe', 'mamba', 'black mamba', 'kb24', 'kb8'],
  'Kristaps Porziņģis': ['porzingis', 'kristaps', 'unicorn'],
  'Kyrie Irving': ['kyrie', 'irving', 'uncle drew'],
  'LaMelo Ball': ['lamelo', 'melo'],
  'Larry Bird': ['bird', 'larry legend'],
  'LeBron James': ['lebron', 'king james', 'lbj', 'bron'],
  'Luka Dončić': ['luka', 'doncic', 'luka magic'],
  'Magic Johnson': ['magic', 'earvin johnson'],
  'Malik Monk': ['monk'],
  'Michael Jordan': ['jordan', 'mj', 'air jordan', 'goat'],
  'Mikal Bridges': ['mikal', 'bridges'],
  'Naz Reid': ['naz', 'reid', 'naz reid'],
  'Nikola Jokić': ['jokic', 'joker', 'big honey'],
  'Norman Powell': ['powell', 'stormin norman'],
  'OG Anunoby': ['anunoby', 'og'],
  'Paolo Banchero': ['paolo', 'banchero'],
  'Payton Pritchard': ['pritchard', 'fastpp'],
  'Rudy Gobert': ['gobert', 'stifle tower'],
  'Shai Gilgeous-Alexander': ['sga', 'shai', 'gilgeous-alexander', 'gilgeous alexander'],
  "Shaquille O'Neal": ['shaq', 'diesel', 'shaquille oneal', 'oneal'],
  'Stephen Curry': ['steph curry', 'steph', 'curry', 'chef curry'],
  'Tim Duncan': ['duncan', 'the big fundamental', 'timmy'],
  'Tracy McGrady': ['tmac', 't-mac', 'mcgrady'],
  'Trae Young': ['trae', 'ice trae'],
  'Tyrese Haliburton': ['haliburton', 'hali'],
  'Tyrese Maxey': ['maxey'],
  'Victor Wembanyama': ['wemby', 'wembanyama', 'alien'],
  'Zion Williamson': ['zion', 'williamson']}

NBA_PLAYER_NICKNAMES = { 'aaron gordon': 'Aaron Gordon',
  'ad': 'Anthony Davis',
  'adebayo': 'Bam Adebayo',
  'ag': 'Aaron Gordon',
  'ai': 'Allen Iverson',
  'air jordan': 'Michael Jordan',
  'alex caruso': 'Alex Caruso',
  'alien': 'Victor Wembanyama',
  'allen iverson': 'Allen Iverson',
  'ant': 'Anthony Edwards',
  'ant man': 'Anthony Edwards',
  'ant-man': 'Anthony Edwards',
  'antetokounmpo': 'Giannis Antetokounmpo',
  'anthony davis': 'Anthony Davis',
  'anthony edwards': 'Anthony Edwards',
  'anunoby': 'OG Anunoby',
  'ar15': 'Austin Reaves',
  'austin reaves': 'Austin Reaves',
  'bald mamba': 'Alex Caruso',
  'bam': 'Bam Adebayo',
  'bam adebayo': 'Bam Adebayo',
  'banchero': 'Paolo Banchero',
  'big honey': 'Nikola Jokić',
  'bird': 'Larry Bird',
  'black mamba': 'Kobe Bryant',
  'bobby': 'Bobby Portis',
  'bobby portis': 'Bobby Portis',
  'book': 'Devin Booker',
  'booker': 'Devin Booker',
  'brandin podziemski': 'Brandin Podziemski',
  'bridges': 'Mikal Bridges',
  'bron': 'LeBron James',
  'brunson': 'Jalen Brunson',
  'butler': 'Jimmy Butler',
  'cam thomas': 'Cam Thomas',
  'carushow': 'Alex Caruso',
  'caruso': 'Alex Caruso',
  'chef curry': 'Stephen Curry',
  'chet': 'Chet Holmgren',
  'chet holmgren': 'Chet Holmgren',
  'coby': 'Coby White',
  'coby white': 'Coby White',
  'curry': 'Stephen Curry',
  'dame': 'Damian Lillard',
  'dame dolla': 'Damian Lillard',
  'damian lillard': 'Damian Lillard',
  'davis': 'Anthony Davis',
  'dbook': 'Devin Booker',
  "de'aaron fox": "De'Aaron Fox",
  'dereck lively': 'Dereck Lively II',
  'dereck lively ii': 'Dereck Lively II',
  'derrick': 'Derrick White',
  'derrick white': 'Derrick White',
  'devin booker': 'Devin Booker',
  'diesel': "Shaquille O'Neal",
  'dirk': 'Dirk Nowitzki',
  'dirk nowitzki': 'Dirk Nowitzki',
  'domantas sabonis': 'Domantas Sabonis',
  'doncic': 'Luka Dončić',
  'donovan mitchell': 'Donovan Mitchell',
  'duncan': 'Tim Duncan',
  'durant': 'Kevin Durant',
  'dwhite': 'Derrick White',
  'earvin johnson': 'Magic Johnson',
  'edwards': 'Anthony Edwards',
  'embiid': 'Joel Embiid',
  'fastpp': 'Payton Pritchard',
  'fox': "De'Aaron Fox",
  'franz': 'Franz Wagner',
  'franz wagner': 'Franz Wagner',
  'giannis': 'Giannis Antetokounmpo',
  'giannis antetokounmpo': 'Giannis Antetokounmpo',
  'gilgeous alexander': 'Shai Gilgeous-Alexander',
  'gilgeous-alexander': 'Shai Gilgeous-Alexander',
  'goat': 'Michael Jordan',
  'gobert': 'Rudy Gobert',
  'gordon': 'Aaron Gordon',
  'greek freak': 'Giannis Antetokounmpo',
  'hakeem': 'Hakeem Olajuwon',
  'hakeem olajuwon': 'Hakeem Olajuwon',
  'hali': 'Tyrese Haliburton',
  'haliburton': 'Tyrese Haliburton',
  'herb': 'Herb Jones',
  'herb jones': 'Herb Jones',
  'holiday': 'Jrue Holiday',
  'holmgren': 'Chet Holmgren',
  'ice trae': 'Trae Young',
  'irving': 'Kyrie Irving',
  'iverson': 'Allen Iverson',
  'ja': 'Ja Morant',
  'ja morant': 'Ja Morant',
  'jaime': 'Jaime Jaquez Jr.',
  'jaime jaquez jr.': 'Jaime Jaquez Jr.',
  'jalen': 'Jalen Brunson',
  'jalen brunson': 'Jalen Brunson',
  'jalen green': 'Jalen Green',
  'jamal murray': 'Jamal Murray',
  'jaquez': 'Jaime Jaquez Jr.',
  'jaquez jr': 'Jaime Jaquez Jr.',
  'jaylen': 'Jaylen Brown',
  'jaylen brown': 'Jaylen Brown',
  'jayson tatum': 'Jayson Tatum',
  'jb': 'Jaylen Brown',
  'jimmy buckets': 'Jimmy Butler',
  'jimmy butler': 'Jimmy Butler',
  'joel embiid': 'Joel Embiid',
  'joker': 'Nikola Jokić',
  'jokic': 'Nikola Jokić',
  'jordan': 'Michael Jordan',
  'jrue': 'Jrue Holiday',
  'jrue holiday': 'Jrue Holiday',
  'jt': 'Jayson Tatum',
  'karl-anthony towns': 'Karl-Anthony Towns',
  'kat': 'Karl-Anthony Towns',
  'kawhi': 'Kawhi Leonard',
  'kawhi leonard': 'Kawhi Leonard',
  'kb24': 'Kobe Bryant',
  'kb8': 'Kobe Bryant',
  'kd': 'Kevin Durant',
  'kevin durant': 'Kevin Durant',
  'king james': 'LeBron James',
  'kobe': 'Kobe Bryant',
  'kobe bryant': 'Kobe Bryant',
  'kristaps': 'Kristaps Porziņģis',
  'kristaps porziņģis': 'Kristaps Porziņģis',
  'kyrie': 'Kyrie Irving',
  'kyrie irving': 'Kyrie Irving',
  'lamelo': 'LaMelo Ball',
  'lamelo ball': 'LaMelo Ball',
  'larry bird': 'Larry Bird',
  'larry legend': 'Larry Bird',
  'lbj': 'LeBron James',
  'lebron': 'LeBron James',
  'lebron james': 'LeBron James',
  'lillard': 'Damian Lillard',
  'lively': 'Dereck Lively II',
  'luka': 'Luka Dončić',
  'luka dončić': 'Luka Dončić',
  'luka magic': 'Luka Dončić',
  'magic': 'Magic Johnson',
  'magic johnson': 'Magic Johnson',
  'malik monk': 'Malik Monk',
  'mamba': 'Kobe Bryant',
  'maxey': 'Tyrese Maxey',
  'mcgrady': 'Tracy McGrady',
  'melo': 'LaMelo Ball',
  'michael jordan': 'Michael Jordan',
  'mikal': 'Mikal Bridges',
  'mikal bridges': 'Mikal Bridges',
  'mitchell': 'Donovan Mitchell',
  'mj': 'Michael Jordan',
  'monk': 'Malik Monk',
  'morant': 'Ja Morant',
  'murray': 'Jamal Murray',
  'naz': 'Naz Reid',
  'naz reid': 'Naz Reid',
  'nikola jokić': 'Nikola Jokić',
  'norman powell': 'Norman Powell',
  'nowitzki': 'Dirk Nowitzki',
  'og': 'OG Anunoby',
  'og anunoby': 'OG Anunoby',
  'olajuwon': 'Hakeem Olajuwon',
  'oneal': "Shaquille O'Neal",
  'paolo': 'Paolo Banchero',
  'paolo banchero': 'Paolo Banchero',
  'payton pritchard': 'Payton Pritchard',
  'playoff jimmy': 'Jimmy Butler',
  'podz': 'Brandin Podziemski',
  'podziemski': 'Brandin Podziemski',
  'portis': 'Bobby Portis',
  'porzingis': 'Kristaps Porziņģis',
  'powell': 'Norman Powell',
  'pritchard': 'Payton Pritchard',
  'reaves': 'Austin Reaves',
  'reid': 'Naz Reid',
  'rudy gobert': 'Rudy Gobert',
  'sabonis': 'Domantas Sabonis',
  'sga': 'Shai Gilgeous-Alexander',
  'shai': 'Shai Gilgeous-Alexander',
  'shai gilgeous-alexander': 'Shai Gilgeous-Alexander',
  'shaq': "Shaquille O'Neal",
  "shaquille o'neal": "Shaquille O'Neal",
  'shaquille oneal': "Shaquille O'Neal",
  'slim reaper': 'Kevin Durant',
  'spida': 'Donovan Mitchell',
  'steph': 'Stephen Curry',
  'steph curry': 'Stephen Curry',
  'stephen curry': 'Stephen Curry',
  'stifle tower': 'Rudy Gobert',
  'stormin norman': 'Norman Powell',
  'swipa': "De'Aaron Fox",
  't-mac': 'Tracy McGrady',
  'tatum': 'Jayson Tatum',
  'the answer': 'Allen Iverson',
  'the big fundamental': 'Tim Duncan',
  'the brow': 'Anthony Davis',
  'the claw': 'Kawhi Leonard',
  'the dream': 'Hakeem Olajuwon',
  'the klaw': 'Kawhi Leonard',
  'the process': 'Joel Embiid',
  'thomas': 'Cam Thomas',
  'tim duncan': 'Tim Duncan',
  'timmy': 'Tim Duncan',
  'tmac': 'Tracy McGrady',
  'towns': 'Karl-Anthony Towns',
  'tracy mcgrady': 'Tracy McGrady',
  'trae': 'Trae Young',
  'trae young': 'Trae Young',
  'tyrese haliburton': 'Tyrese Haliburton',
  'tyrese maxey': 'Tyrese Maxey',
  'uncle drew': 'Kyrie Irving',
  'unicorn': 'Kristaps Porziņģis',
  'victor wembanyama': 'Victor Wembanyama',
  'wagner': 'Franz Wagner',
  'wembanyama': 'Victor Wembanyama',
  'wemby': 'Victor Wembanyama',
  'williamson': 'Zion Williamson',
  'zion': 'Zion Williamson',
  'zion williamson': 'Zion Williamson'}

NBA_LEGACY_CARD_MAPPINGS = { 'amy-chetholmgren-89': 'amy-chet-89',
  'amy-jalen-89': 'amy-brunson-92',
  'amy-jamalmurray-89': 'amy-murray-89',
  'amy-lameloball-89': 'amy-lamelo-89',
  'amy-paolobanchero-89': 'amy-paolo-90',
  'amy-pawlo-89': 'amy-paolo-90',
  'amy-sabonis-90': 'amy-kat-90',
  'amy-tymax-90': 'amy-brunson-92',
  'dia-anthonyedwards-95': 'dia-ant-95',
  'dia-jamorant-93': 'dia-morant-93',
  'dia-shaigilgeousalexander-95': 'dia-sga-95',
  'dm-kobebryant-99': 'dm-kobe-99',
  'dm-larrybird-99': 'dm-bird-99',
  'dm-lebronjames-99': 'dm-lebron-99',
  'dm-magicjohnson-99': 'dm-magic-99',
  'dm-michaeljordan-99': 'dm-jordan-99',
  'dm-mj-99': 'dm-jordan-99',
  'dm-shaquilleoneal-99': 'dm-shaq-99',
  'dm-stephencurry-99': 'dm-curry-99',
  'dm-victorwembanyama-99': 'dm-wemby-99',
  'go-alleniverson-97': 'go-iverson-97',
  'go-anthonydavis-97': 'go-ad-97',
  'go-jaysontatum-98': 'go-tatum-98',
  'go-jimmybutler-97': 'go-butler-97',
  'go-joelembiid-98': 'go-embiid-98',
  'go-kawhileonard-97': 'go-kawhi-97',
  'go-lukadoncic-98': 'go-luka-98',
  'go-nikolajokic-98': 'go-jokic-98',
  'go-tracymcgrady-98': 'go-tmac-98',
  'gold-alexcaruso-81': 'gold-caruso-81',
  'gold-herb-82': 'gold-anunoby-82',
  'gold-powell-80': 'gold-mikal-82',
  'gold-pritchard-80': 'gold-white-82',
  'gold-thomas-82': 'gold-reaves-82',
  'ruby-aarongordon-85': 'ruby-gordon-85',
  'ruby-austinreaves-84': 'ruby-reaves-84',
  'ruby-cade-86': 'ruby-reaves-84',
  'ruby-coby-85': 'ruby-mikal-85',
  'ruby-derrickwhite-86': 'ruby-white-86',
  'ruby-gobert-86': 'ruby-gordon-85',
  'ruby-herro-86': 'ruby-white-86',
  'ruby-ingram-86': 'ruby-anunoby-85',
  'ruby-lauri-85': 'ruby-gordon-85',
  'ruby-lavine-86': 'ruby-white-86',
  'ruby-maxey-87': 'ruby-white-86',
  'ruby-mikalbridges-85': 'ruby-mikal-85',
  'ruby-oganunoby-85': 'ruby-anunoby-85',
  'ruby-porzingis-87': 'ruby-gordon-85',
  'ruby-scottie-86': 'ruby-anunoby-85',
  'ruby-wagner-86': 'ruby-mikal-85',
  'go-curry-97': 'dm-curry-99',
  'go-duncan-98': 'dm-timduncan-99',
  'go-durant-96': 'dm-kd-99',
  'go-jokic-97': 'go-jokic-98'}

NBA_FUSION_GIF_MAPPINGS = {
  'dm-billrussell-99': {
    'name': 'Bill Russell',
    'gif_url': 'https://media.tenor.com/-uKWiG9YwiYAAAAM/bill-russell.gif',
    'flavor_text': '🏆 The greatest winner in basketball history has ascended'
  },
  'dm-bird-99': {
    'name': 'Larry Bird',
    'gif_url': 'https://media.tenor.com/785iV9CCFTcAAAAM/larry-bird-robert-parish.gif',
    'flavor_text': '🧊 Larry Legend is ice cold and completely untouchable'
  },
  'dm-curry-99': {
    'name': 'Stephen Curry',
    'gif_url': 'https://media.tenor.com/Oy2ncwqiZO8AAAAM/night-night-nighty-night.gif',
    'flavor_text': '🍳 Curry has cooked the entire universe from half court'
  },
  'dm-giannis-99': {
    'name': 'Giannis Antetokounmpo',
    'gif_url': 'https://media.tenor.com/KJeGdvrcQvMAAAAM/milwaukee-bucks-giannis-antetokounmpo.gif',
    'flavor_text': '⚡ The Greek Freak has become a full deity'
  },
  'dm-hakeemolajuwon-99': {
    'name': 'Hakeem Olajuwon',
    'gif_url': 'https://media.tenor.com/u0aplK7iUvYAAAAM/hakeem-turn-around.gif',
    'flavor_text': '👻 The Dream Shake is now an unsolvable mystery'
  },
  'dm-jordan-99': {
    'name': 'Michael Jordan',
    'gif_url': 'https://media.tenor.com/-5II3eZiaJcAAAAM/michael-jordan-basketball.gif',
    'flavor_text': '🐐 His Airness has transcended basketball itself'
  },
  'dm-kareemabduljabbar-99': {
    'name': 'Kareem Abdul-Jabbar',
    'gif_url': 'https://media.tenor.com/JEnX7ebK0Z0AAAAM/kareem-kareem-skyhook.gif',
    'flavor_text': '🌀 The Skyhook is beyond all human comprehension'
  },
  'dm-kd-99': {
    'name': 'Kevin Durant',
    'gif_url': 'https://media.tenor.com/7ruKh0zDurUAAAAM/dunk-kevin-durant-dunk.gif',
    'flavor_text': '🎯 The Slim Reaper cannot be stopped by anyone'
  },
  'dm-kobe-99': {
    'name': 'Kobe Bryant',
    'gif_url': 'https://media.tenor.com/xUF6L_2N2ZAAAAAM/nba-saiyan.gif',
    'flavor_text': '🐍 The Black Mamba has ascended beyond all limits'
  },
  'dm-lebron-99': {
    'name': 'LeBron James',
    'gif_url': 'https://media.tenor.com/lquFMyMh8zYAAAAM/lebron-james-dunk.gif',
    'flavor_text': '👑 The King has entered God Mode'
  },
  'dm-magic-99': {
    'name': 'Magic Johnson',
    'gif_url': 'https://media.tenor.com/zcX1Snd2CtsAAAAM/magic-johnson.gif',
    'flavor_text': '✨ Showtime has never looked this magical'
  },
  'dm-shaq-99': {
    'name': "Shaquille O'Neal",
    'gif_url': 'https://media.tenor.com/kuyCaCZWKCwAAAAM/shaquille-oneal-basketball.gif',
    'flavor_text': '💥 Shaq Diesel has gone absolutely nuclear'
  },
  'dm-timduncan-99': {
    'name': 'Tim Duncan',
    'gif_url': 'https://media.tenor.com/69cPUdgnQxwAAAAM/tim-duncan.gif',
    'flavor_text': '🏆 The Big Fundamental has become fundamentally unstoppable'
  },
  'dm-wemby-99': {
    'name': 'Victor Wembanyama',
    'gif_url': 'https://media.tenor.com/XfmGUCYiEUEAAAAM/victor-wembanyama-wembanyama.gif',
    'flavor_text': '👽 Wemby has confirmed he is not from this planet'
  },
  'dm-wiltchamberlain-99': {
    'name': 'Wilt Chamberlain',
    'gif_url': 'https://media.tenor.com/jqrvfLdQhZYAAAAM/wilt-chamberlain-basketball.gif',
    'flavor_text': '👹 Wilt the Stilt has become a god among men'
  },
  'go-ad-97': {
    'name': 'Anthony Davis',
    'gif_url': 'https://media.tenor.com/q7s8-zGWp-8AAAAM/lakers.gif',
    'flavor_text': '👁️ The Brow has unlocked complete basketball domination'
  },
  'go-alleniverson-97': {
    'name': 'Allen Iverson',
    'gif_url': 'https://media.tenor.com/EEdRX92hjD4AAAAM/allen-iverson-michael-jordan.gif',
    'flavor_text': '💨 The Answer moves faster than reality itself'
  },
  'go-alonzomourning-97': {
    'name': 'Alonzo Mourning',
    'gif_url': 'https://media.tenor.com/wF9FQunfa6YAAAAM/alonzo-mourning.gif',
    'flavor_text': '🛡️ Zo has rejected every shot in basketball history'
  },
  'go-bobcousy-97': {
    'name': 'Bob Cousy',
    'gif_url': 'https://media.tenor.com/H0foamBzrn4AAAAM/bob-cousy-crossover.gif',
    'flavor_text': '🎩 The Cooz invented basketball magic before it had a name'
  },
  'go-butler-97': {
    'name': 'Jimmy Butler',
    'gif_url': 'https://media.tenor.com/LlA95VeBO4YAAAAM/miamiheat-jimmybutler.gif',
    'flavor_text': '🔥 Jimmy Buckets has grinded his way to immortality'
  },
  'go-carmeloanthony-97': {
    'name': 'Carmelo Anthony',
    'gif_url': 'https://media.tenor.com/4O4z-bR2qMMAAAAM/carmelo-anthony-melo.gif',
    'flavor_text': "🍊 Melo's midrange game is a form of poetry no one else can write"
  },
  'go-charlesbarkley-98': {
    'name': 'Charles Barkley',
    'gif_url': 'https://media.tenor.com/BBAgR634QDwAAAAM/charles-barkley-sir-charles.gif',
    'flavor_text': '💪 Sir Charles has become an immovable force of nature'
  },
  'go-chrispaul-97': {
    'name': 'Chris Paul',
    'gif_url': 'https://media.tenor.com/QqhVvvcJ-FgAAAAM/chris-paul-chrispaul.gif',
    'flavor_text': '🧠 The Point God controls the game from another dimension'
  },
  'go-clydedrexler-98': {
    'name': 'Clyde Drexler',
    'gif_url': 'https://media.tenor.com/aTB1CJylK64AAAAM/clyde-drexler-nba.gif',
    'flavor_text': '🌊 Clyde the Glide has reached breathtaking new heights'
  },
  'go-damianlillard-98': {
    'name': 'Damian Lillard',
    'gif_url': 'https://media.tenor.com/B7vlYeVyouYAAAAM/dame-lillard.gif',
    'flavor_text': '⏰ Dame Time has become completely infinite'
  },
  'go-davidrobinson-98': {
    'name': 'David Robinson',
    'gif_url': 'https://media.tenor.com/llHrhs7rvBoAAAAM/david-robinson-spurs.gif',
    'flavor_text': '⚓ The Admiral has commanded complete basketball domination'
  },
  'go-dikembemutombo-97': {
    'name': 'Dikembe Mutombo',
    'gif_url': 'https://media.tenor.com/Q5knp6bJF7wAAAAM/no-no-no-sports.gif',
    'flavor_text': "☝️ Not in Dikembe's house. Not today. Not ever."
  },
  'go-dirknowitzki-98': {
    'name': 'Dirk Nowitzki',
    'gif_url': 'https://media.tenor.com/l0iTUt9dWAgAAAAM/dirk-nowitzki-dallas-mavericks.gif',
    'flavor_text': "🇩🇪 Nowitzki's fadeaway defies the laws of physics"
  },
  'go-dominiquewilkins-98': {
    'name': 'Dominique Wilkins',
    'gif_url': 'https://media.tenor.com/23AQEdGjo9kAAAAM/dominique-wilkins-windmill-dunk.gif',
    'flavor_text': '🦅 The Human Highlight Film has gone completely supernatural'
  },
  'go-donovanmitchell-97': {
    'name': 'Donovan Mitchell',
    'gif_url': 'https://media.tenor.com/IXx9Sy0zangAAAAM/utah-jazz-donovan-mitchell.gif',
    'flavor_text': '🕷️ Spida Mitchell has spun a web no one can escape'
  },
  'go-dwighthoward-97': {
    'name': 'Dwight Howard',
    'gif_url': 'https://media.tenor.com/UoIe4hF35J0AAAAM/dunk-contest.gif',
    'flavor_text': '🦸 Superman has taken complete ownership of the entire paint'
  },
  'go-dwyanewade-98': {
    'name': 'Dwyane Wade',
    'gif_url': 'https://media.tenor.com/wQqVEkxIPAkAAAAM/dwayne-wade-nba.gif',
    'flavor_text': '⚡ The Flash has reached absolute maximum velocity'
  },
  'go-elginbaylor-98': {
    'name': 'Elgin Baylor',
    'gif_url': '',
    'flavor_text': '✈️ Elgin Baylor was flying before flying was even possible'
  },
  'go-embiid-98': {
    'name': 'Joel Embiid',
    'gif_url': 'https://media.tenor.com/dZnUrWgomFAAAAAM/joel-embiid-slam.gif',
    'flavor_text': '🌍 The Process is now complete and totally unstoppable'
  },
  'go-garypayton-97': {
    'name': 'Gary Payton',
    'gif_url': 'https://media.tenor.com/NhVNJ-Nh2eUAAAAM/seattle-supersonics-gary-payton.gif',
    'flavor_text': '🧤 The Glove has locked down the entire universe'
  },
  'go-granthill-97': {
    'name': 'Grant Hill',
    'gif_url': 'https://media.tenor.com/sfW2B6vJlHcAAAAM/grant-hill-dunk.gif',
    'flavor_text': '🌟 Grant Hill showed the world what a complete player looks like'
  },
  'go-isiahthomas-98': {
    'name': 'Isiah Thomas',
    'gif_url': 'https://media.tenor.com/kvyhSwhFGI4AAAAM/detroit-pistons-isiah-thomas.gif',
    'flavor_text': '⚡ Zeke has proven size means absolutely nothing'
  },
  'go-iverson-97': {
    'name': 'Allen Iverson',
    'gif_url': 'https://media.tenor.com/1EWb9d-a80cAAAAM/iverson-crossover.gif',
    'flavor_text': '💨 The Answer moves faster than reality itself'
  },
  'go-jamesharden-97': {
    'name': 'James Harden',
    'gif_url': 'https://media.tenor.com/PzFNraX8AdkAAAAM/houston-rockets-stir.gif',
    'flavor_text': "🧔 The Beard's step back has become physically impossible to guard"
  },
  'go-jasonkidd-98': {
    'name': 'Jason Kidd',
    'gif_url': 'https://media.tenor.com/QEvwiRiFDlAAAAAM/jason-kidd.gif',
    'flavor_text': '👁️ Kidd saw the game three plays ahead of everyone else'
  },
  'go-jerrywest-98': {
    'name': 'Jerry West',
    'gif_url': 'https://media.tenor.com/jPy4ArbPHUQAAAAM/jerry-west-lakers.gif',
    'flavor_text': '🏀 The Logo himself has come to life'
  },
  'go-johnstockton-98': {
    'name': 'John Stockton',
    'gif_url': 'https://media.tenor.com/4SAdW1hPFXwAAAAM/jon-stockton-assist.gif',
    'flavor_text': '🎯 Stockton has become the puppet master of basketball'
  },
  'go-jokic-98': {
    'name': 'Nikola Jokic',
    'gif_url': 'https://media.tenor.com/MOufHecLk6IAAAAM/sports-sportsmanias.gif',
    'flavor_text': '♟️ The Joker has revealed his final unstoppable form'
  },
  'go-juliuserving-98': {
    'name': 'Julius Erving',
    'gif_url': 'https://media.tenor.com/Nr762QJup18AAAAM/erving-sixers.gif',
    'flavor_text': '🩺 Dr J has prescribed a legendary dose of greatness'
  },
  'go-karlmalone-98': {
    'name': 'Karl Malone',
    'gif_url': 'https://media.tenor.com/LTIxrHUvj8kAAAAM/karl-malone-the-mail-man.gif',
    'flavor_text': '📬 The Mailman always delivers in legendary form'
  },
  'go-kawhi-97': {
    'name': 'Kawhi Leonard',
    'gif_url': 'https://media.tenor.com/wOov1s3fCMEAAAAM/kawhi-kawhi-leonard.gif',
    'flavor_text': '🤖 The Klaw has fully activated terminator mode'
  },
  'go-kevingarnett-98': {
    'name': 'Kevin Garnett',
    'gif_url': 'https://media.tenor.com/1g9AnZZbvDMAAAAM/kevin-garnett.gif',
    'flavor_text': "🔥 KG's intensity has shattered every limit imaginable"
  },
  'go-kyrieirving-98': {
    'name': 'Kyrie Irving',
    'gif_url': 'https://media.tenor.com/MltYmfAReOcAAAAM/kyrie-handles.gif',
    'flavor_text': "🌀 Uncle Drew's handles have completely broken the matrix"
  },
  'go-luka-98': {
    'name': 'Luka Doncic',
    'gif_url': 'https://media.tenor.com/C9ABcyLH9l4AAAAM/luka-doncic-stepback.gif',
    'flavor_text': '🌟 Luka Magic has gone completely beyond human limits'
  },
  'go-mosesmalone-98': {
    'name': 'Moses Malone',
    'gif_url': '',
    'flavor_text': '💪 Moses has led his team to the promised land'
  },
  'go-oscarrobertson-98': {
    'name': 'Oscar Robertson',
    'gif_url': '',
    'flavor_text': '📊 The Big O has redefined what is humanly possible'
  },
  'go-patrickewing-98': {
    'name': 'Patrick Ewing',
    'gif_url': 'https://media.tenor.com/WVf7ugpBhoEAAAAM/patrick-ewing-33.gif',
    'flavor_text': '🏙️ Ewing has become the guardian of New York'
  },
  'go-paulgeorge-98': {
    'name': 'Paul George',
    'gif_url': 'https://media.tenor.com/G8eP7Zgy_-YAAAAM/dunk-paul-george.gif',
    'flavor_text': '🌙 PG has elevated his game to another dimension entirely'
  },
  'go-paulpierce-97': {
    'name': 'Paul Pierce',
    'gif_url': 'https://media.tenor.com/xVWgjAhAlZcAAAAM/paul-pierce-pierce.gif',
    'flavor_text': '💚 The Truth cannot be denied or stopped'
  },
  'go-petemaravich-97': {
    'name': 'Pete Maravich',
    'gif_url': 'https://media.tenor.com/9nw7rSUBdwIAAAAM/pete-maravich-pistol-pete.gif',
    'flavor_text': '🔫 Pistol Pete shoots from dimensions no one else can reach'
  },
  'go-rayallen-97': {
    'name': 'Ray Allen',
    'gif_url': 'https://media.tenor.com/-pDys2heFfQAAAAM/ray-allen.gif',
    'flavor_text': '🎯 The purest shooter to ever grace the hardwood'
  },
  'go-reggiemiller-97': {
    'name': 'Reggie Miller',
    'gif_url': 'https://media.tenor.com/p_99fxGEA4UAAAAM/reggie-miller-choke.gif',
    'flavor_text': '🤌 Reggie Miller lives for the moment everyone else fears'
  },
  'go-rickbarry-97': {
    'name': 'Rick Barry',
    'gif_url': '',
    'flavor_text': '🎯 Rick Barry did it his own way and it worked every single time'
  },
  'go-russellwestbrook-97': {
    'name': 'Russell Westbrook',
    'gif_url': 'https://media.tenor.com/HliWh4j2SBsAAAAM/russel-westbrook-nba.gif',
    'flavor_text': '💢 Brodie runs on a different fuel than every other human being'
  },
  'go-scottiepippen-98': {
    'name': 'Scottie Pippen',
    'gif_url': 'https://media.tenor.com/4zjloKDWg6sAAAAM/scottie-pippen.gif',
    'flavor_text': '🦸 Pip has stepped out of the shadow and into legend'
  },
  'go-stevenash-98': {
    'name': 'Steve Nash',
    'gif_url': 'https://media.tenor.com/75ewi4a2u5UAAAAM/steve-nash.gif',
    'flavor_text': '🎩 Nash turned basketball into an art form nobody else could paint'
  },
  'go-tatum-98': {
    'name': 'Jayson Tatum',
    'gif_url': 'https://media.tenor.com/JegpKDR4F3gAAAAM/jayson-tatum-dunk.gif',
    'flavor_text': '🍀 Tatum has become the new face of Boston legend'
  },
  'go-timhardaway-97': {
    'name': 'Tim Hardaway',
    'gif_url': 'https://media.tenor.com/K-6KCIpOdocAAAAM/tim-hardaway-golden-state.gif',
    'flavor_text': '💫 The UTEP Two Step has crossed over into legend'
  },
  'go-tmac-98': {
    'name': 'Tracy McGrady',
    'gif_url': 'https://media.tenor.com/5GVprx8UYhAAAAAM/tracy-mcgrady-toronto-raptors.gif',
    'flavor_text': '⚡ T-Mac has unlocked unlimited scoring mode'
  },
  'go-tonyparker-97': {
    'name': 'Tony Parker',
    'gif_url': 'https://media.tenor.com/7mw-CscArwoAAAAM/tony-parker-spurs.gif',
    'flavor_text': '🇫🇷 The French Prince floated past every defender in history'
  },
  'go-vincecarter-97': {
    'name': 'Vince Carter',
    'gif_url': 'https://media.tenor.com/8N_RlZgzqSoAAAAM/vince-carter-vince.gif',
    'flavor_text': '🦅 Vinsanity has taken flight into the stratosphere'
  },
  'go-waltfrazier-98': {
    'name': 'Walt Frazier',
    'gif_url': 'https://media.tenor.com/EU8UIOtlkKIAAAAM/walt-frazier.gif',
    'flavor_text': '😎 Clyde is too cool for this planet'
  },
  'go-willisreed-97': {
    'name': 'Willis Reed',
    'gif_url': '',
    'flavor_text': '❤️ The heart of a champion cannot be measured'
  }
}

NBA_PLAYER_IMG_IDS = { 'Aaron Gordon': '203932',
  'Alex Caruso': '1627936',
  'Allen Iverson': '947',
  'Alperen Sengun': '1641711',
  'Andre Iguodala': '2738',
  'Andre Iguodala (2015)': '2738',
  'Anthony Davis': '203076',
  'Anthony Edwards': '1630162',
  'Austin Reaves': '1631260',
  'Bam Adebayo': '1628389',
  'Bobby Portis': '1626171',
  'Brandin Podziemski': '1641764',
  'Brandon Ingram': '1627742',
  'Brook Lopez': '201572',
  'Cade Cunningham': '1630595',
  'Cam Thomas': '1630560',
  'Carter Bryant': '1643126',
  'Chet Holmgren': '1631096',
  'Chris Paul': '101108',
  'Coby White': '1629632',
  "D'Angelo Russell": '1626156',
  'Damian Lillard': '203081',
  'Darius Garland': '1629636',
  "De'Aaron Fox": '1628368',
  'Dereck Lively II': '1641726',
  'Derrick White': '1628401',
  'Devin Booker': '1626164',
  'Dirk Nowitzki': '1717',
  'Domantas Sabonis': '1627734',
  'Donovan Mitchell': '1628378',
  'Draymond Green': '203110',
  'Dwyane Wade': '2548',
  'Evan Mobley': '1630596',
  'Franz Wagner': '1630532',
  'Fred VanVleet': '1627832',
  'Giannis Antetokounmpo': '203507',
  'Hakeem Olajuwon': '165',
  'Herb Jones': '1630529',
  'Ja Morant': '1629630',
  'Jaime Jaquez Jr.': '1631170',
  'Jalen Brunson': '1628973',
  'Jalen Green': '1630224',
  'Jamal Murray': '1627750',
  'James Harden': '203114',
  'Jaren Jackson Jr.': '1628991',
  'Jaylen Brown': '1627759',
  'Jayson Tatum': '1628369',
  'Jimmy Butler': '202710',
  'Joel Embiid': '203954',
  'Jrue Holiday': '201950',
  'Julius Randle': '203944',
  'Karl-Anthony Towns': '1626157',
  'Kawhi Leonard': '202695',
  'Kevin Durant': '201142',
  'Khris Middleton': '203077',
  'Klay Thompson': '202691',
  'Klay Thompson (2016)': '202691',
  'Kobe Bryant': '977',
  'Kristaps Porzingis': '204001',
  'Kristaps Porziņģis': '204001',
  'Kyle Lowry': '200768',
  'Kyrie Irving': '202681',
  'LaMelo Ball': '1630163',
  'Larry Bird': '1449',
  'Lauri Markkanen': '1628374',
  'LeBron James': '2544',
  'Luka Doncic': '1629029',
  'Luka Dončić': '1629029',
  'Magic Johnson': '77142',
  'Malik Monk': '1628370',
  'Michael Jordan': '893',
  'Mikal Bridges': '1628969',
  'Miles Bridges': '1628970',
  'Naz Reid': '1629675',
  'Nikola Jokic': '203999',
  'Nikola Jokić': '203999',
  'Norman Powell': '1626181',
  'OG Anunoby': '1628384',
  'Paolo Banchero': '1631094',
  'Pascal Siakam': '1627783',
  'Pau Gasol': '2200',
  'Paul George': '202331',
  'Payton Pritchard': '1630202',
  'RJ Barrett': '1629628',
  'Robert Williams III': '1629057',
  'Rudy Gobert': '203497',
  'Russell Westbrook': '201566',
  'Ryan Rollins': '1631157',
  'Scottie Barnes': '1630567',
  'Scottie Pippen': '967',
  'Shai Gilgeous-Alexander': '1628983',
  "Shaquille O'Neal": '406',
  'Stephen Curry': '201939',
  'Tim Duncan': '1495',
  'Tobias Harris': '202699',
  'Tracy McGrady': '1503',
  'Trae Young': '1629027',
  'Tyler Herro': '1629625',
  'Tyrese Haliburton': '1630169',
  'Tyrese Maxey': '1630178',
  'Victor Wembanyama': '1641705',
  'Zach LaVine': '203897',
  'Zion Williamson': '1629627'}

NBA_PLAYER_MOMENT_ACTION_URLS = { 'aaron gordon': 'https://upload.wikimedia.org/wikipedia/commons/8/89/Aaron_Gordon_2023.jpg',
  'alex caruso': 'https://upload.wikimedia.org/wikipedia/commons/2/29/Alex_Caruso_%2851888062828%29_%28cropped%29.jpg',
  'allen iverson': 'https://upload.wikimedia.org/wikipedia/commons/f/f4/Allen_Iverson_08_B.jpg',
  'alonzo mourning': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b7/Alonzo_Mourning.jpg/1280px-Alonzo_Mourning.jpg',
  'andre iguodala': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/58/Heat_Andre_Iguodala_%28cropped%29.jpg/1280px-Heat_Andre_Iguodala_%28cropped%29.jpg',
  'anthony davis': 'https://upload.wikimedia.org/wikipedia/commons/3/36/Anthony_Davis_2020.jpg',
  'anthony edwards': 'https://upload.wikimedia.org/wikipedia/commons/1/10/Anthony_Edwards_2024.jpg',
  'austin reaves': 'https://upload.wikimedia.org/wikipedia/commons/5/52/Austin_Reaves_2023.jpg',
  'bam adebayo': 'https://upload.wikimedia.org/wikipedia/commons/f/f0/Adebayo_Hachimura_%28cropped%29.jpg',
  'bill russell': 'https://upload.wikimedia.org/wikipedia/commons/d/d3/Bill_russell_dribbling_%28cropped%29.jpg',
  'bill walton': 'https://upload.wikimedia.org/wikipedia/commons/5/54/Bill_walton_blazers_photo.jpg',
  'blake griffin': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/7e/Blake_Griffin_with_ball_20131118_Clippers_v_Grizzles.jpg/1280px-Blake_Griffin_with_ball_20131118_Clippers_v_Grizzles.jpg',
  'bob cousy': 'https://upload.wikimedia.org/wikipedia/commons/c/c5/Bob_Cousy_%281%29.jpeg',
  'carmelo anthony': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/27/Carmelo_Anthony_at_2025_NBA_All_Star_Weekend_%28cropped%29.jpg/1280px-Carmelo_Anthony_at_2025_NBA_All_Star_Weekend_%28cropped%29.jpg',
  'charles barkley': 'https://upload.wikimedia.org/wikipedia/commons/f/f6/Charles_Barkley_representing_the_1992_Dream_Team.jpg',
  'chet holmgren': 'https://upload.wikimedia.org/wikipedia/commons/b/b8/Chet_Holmgren_2024.jpg',
  'chris paul': 'https://upload.wikimedia.org/wikipedia/commons/a/ad/Chris_Paul_%282022_All-Star_Weekend%29_%28cropped%29.jpg',
  'clyde drexler': 'https://upload.wikimedia.org/wikipedia/commons/6/62/Clyde_Drexler_01.jpg',
  'damian lillard': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/8/8e/Damian_Lillard_%282021%29_%28cropped%29.jpg/1280px-Damian_Lillard_%282021%29_%28cropped%29.jpg',
  'david robinson': 'https://upload.wikimedia.org/wikipedia/commons/c/c9/David_Robinson_%28Team_USA%29.jpg',
  'deaaron fox': 'https://upload.wikimedia.org/wikipedia/commons/f/fa/De%27Aaron_Fox_%28cropped%29.jpg',
  'derrick white': 'https://upload.wikimedia.org/wikipedia/commons/1/18/Derrick_White_2024.jpg',
  'devin booker': 'https://upload.wikimedia.org/wikipedia/commons/2/22/Devin_Booker%2C_Olympic_Games_2024_%28cropped%29.jpg',
  'dikembe mutombo': 'https://upload.wikimedia.org/wikipedia/commons/e/e8/Lipofsky-Dikembe_Mutombo_%28cropped%29.jpg',
  'dirk nowitzki': 'https://upload.wikimedia.org/wikipedia/commons/5/54/Dirk_Nowitzki_al_rimbalzo.jpg',
  'dominique wilkins': 'https://upload.wikimedia.org/wikipedia/commons/4/4e/Dominique_Wilkins_%2851914585633%29.jpg',
  'donovan mitchell': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/39/Donovan_Mitchell_Pregame.jpg/1280px-Donovan_Mitchell_Pregame.jpg',
  'draymond green': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/9/99/Draymond_Green_2022.jpg/1280px-Draymond_Green_2022.jpg',
  'dwight howard': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/41/Dwight_Howard_pre-game_%28cropped%29.jpg/1280px-Dwight_Howard_pre-game_%28cropped%29.jpg',
  'dwyane wade': 'https://upload.wikimedia.org/wikipedia/commons/8/88/Dwyane_Wade_2012.jpg',
  'elgin baylor': 'https://upload.wikimedia.org/wikipedia/commons/e/e5/Elgin_Baylor_Night_program-%28cropped%29.jpg',
  'gary payton': 'https://upload.wikimedia.org/wikipedia/commons/1/14/Gary_Payton%2C_Miami_Heat_circa_2007_%28cropped%29.jpg',
  'giannis antetokounmpo': 'https://upload.wikimedia.org/wikipedia/commons/7/7f/Giannis_Antetokoummpo_%2831669417562%29.jpg',
  'grant hill': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/0/05/Grant_Hill_2007-12-08.jpg/1280px-Grant_Hill_2007-12-08.jpg',
  'hakeem olajuwon': 'https://upload.wikimedia.org/wikipedia/commons/b/bd/Hakeem.jpg',
  'isiah thomas': 'https://upload.wikimedia.org/wikipedia/commons/5/50/Isiah-thomas_detroit-v-new-york_1985.jpg',
  'ja morant': 'https://upload.wikimedia.org/wikipedia/commons/1/14/Ja_Morant_2022.jpg',
  'jalen brunson': 'https://upload.wikimedia.org/wikipedia/commons/f/f2/Jalen_Brunson_2023_%28cropped%29.jpg',
  'jamal murray': 'https://upload.wikimedia.org/wikipedia/commons/0/07/Jamal_Murray_2023.jpg',
  'james harden': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/6/63/Harden_dribbling_midcourt%2C_Cavaliers_vs_Nets_on_January_17%2C_2022_%28cropped%29.jpg/1280px-Harden_dribbling_midcourt%2C_Cavaliers_vs_Nets_on_January_17%2C_2022_%28cropped%29.jpg',
  'jason kidd': 'https://upload.wikimedia.org/wikipedia/commons/8/84/Jason_Kidd_Nets_coach_cropped.jpg',
  'jaylen brown': 'https://upload.wikimedia.org/wikipedia/commons/8/84/Celtics_at_Wizards_2024-12-015_%28cropped%29_%28cropped%29.jpg',
  'jayson tatum': 'https://upload.wikimedia.org/wikipedia/commons/c/c8/Jayson_Tatum_Parade_2024.jpg',
  'jerry west': 'https://upload.wikimedia.org/wikipedia/commons/5/5a/Jerry_West_1972.jpeg',
  'jimmy butler': 'https://upload.wikimedia.org/wikipedia/commons/b/be/Jimmy_Butler_2020.jpg',
  'joel embiid': 'https://upload.wikimedia.org/wikipedia/commons/1/13/Joel_Embiid_2019.jpg',
  'john stockton': 'https://upload.wikimedia.org/wikipedia/commons/c/cf/John_Stockton_2022.jpg',
  'jrue holiday': 'https://upload.wikimedia.org/wikipedia/commons/b/ba/Celtics_at_Wizards_2024-12-021_%28cropped%29.jpg',
  'julius erving': 'https://upload.wikimedia.org/wikipedia/commons/0/0d/Julius_Erving_2016.jpg',
  'kareem abdul-jabbar': 'https://upload.wikimedia.org/wikipedia/commons/a/a0/Kareem_Abdul-Jabbar_May_2014.jpg',
  'karl malone': 'https://upload.wikimedia.org/wikipedia/commons/e/e5/NBA_HOF%E2%80%99er_Karl_Malone_visits_Barksdale_%289%29_%28cropped%29.jpg',
  'karl-anthony towns': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/55/Karl-Anthony_Towns_%2851914283512%29_%28cropped%29_%28cropped%29.jpg/1280px-Karl-Anthony_Towns_%2851914283512%29_%28cropped%29_%28cropped%29.jpg',
  'kawhi leonard': 'https://upload.wikimedia.org/wikipedia/commons/5/5a/Kawhi_Leonard_2019.jpg',
  'kevin durant': 'https://upload.wikimedia.org/wikipedia/commons/4/4a/Jonas_Maciulis_attacks_the_basket_%28cropped%29.jpg',
  'kevin garnett': 'https://upload.wikimedia.org/wikipedia/commons/6/60/Kevin_Garnett_2008-01-13.jpg',
  'klay thompson': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/8/81/Klay_Thompson_%28cropped%29.jpg/1280px-Klay_Thompson_%28cropped%29.jpg',
  'kobe bryant': 'https://upload.wikimedia.org/wikipedia/commons/4/43/Kobe_Bryant_Jumper_07_%28cropped%29.jpg',
  'kyrie irving': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/27/Kyrie_Irving_%2851830909437%29_%28cropped%29.jpg/1280px-Kyrie_Irving_%2851830909437%29_%28cropped%29.jpg',
  'lamelo ball': 'https://upload.wikimedia.org/wikipedia/commons/b/b9/LaMelo_Ball_2022.jpg',
  'larry bird': 'https://upload.wikimedia.org/wikipedia/commons/e/ef/December_1983_One_on_One_Dr_J_vs_Larry_Bird_advertisement_by_Electronic_Arts_%28cropped%29_%28cropped%29.jpg',
  'lebron james': 'https://upload.wikimedia.org/wikipedia/commons/2/25/Lebron_wizards_2017_%28cropped%29.jpg',
  'luka doncic': 'https://upload.wikimedia.org/wikipedia/commons/b/be/Luka_Don%C4%8Di%C4%87_and_Marines%2C_2026_%28cropped%29.jpg',
  'magic johnson': 'https://upload.wikimedia.org/wikipedia/commons/e/e8/Pat_Riley_and_Earvin_%22Magic%22_Johnsonat_the_Century_Plaza_%28cropped%29.jpg',
  'manu ginobili': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/33/Manu_Ginobili_Spurs-Magic011_%28cropped%29.jpg/1280px-Manu_Ginobili_Spurs-Magic011_%28cropped%29.jpg',
  'michael jordan': 'https://upload.wikimedia.org/wikipedia/commons/4/43/Steve_Lipfosky_--_Michael_Jordan_%281997%29.jpg',
  'mikal bridges': 'https://upload.wikimedia.org/wikipedia/commons/3/3a/Mikal_Bridges_2023.jpg',
  'moses malone': 'https://upload.wikimedia.org/wikipedia/commons/a/a1/Moses_Malone_cropped_portrait.jpg',
  'nikola jokic': 'https://upload.wikimedia.org/wikipedia/commons/7/7e/Nikola_Jokic_free_throw_%28cropped%29.jpg',
  'og anunoby': 'https://upload.wikimedia.org/wikipedia/commons/3/30/OG_Anunoby_2024.jpg',
  'oscar robertson': 'https://upload.wikimedia.org/wikipedia/commons/a/a1/Oscar_Robertson_1960.jpeg',
  'paolo banchero': 'https://upload.wikimedia.org/wikipedia/commons/1/1e/Paolo_Banchero_2024.jpg',
  'patrick ewing': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/0/05/Patrick_Ewing_2021_%28cropped%29.jpg/1280px-Patrick_Ewing_2021_%28cropped%29.jpg',
  'paul george': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/71/1_paul_george_2026_%28cropped%29.jpg/1280px-1_paul_george_2026_%28cropped%29.jpg',
  'paul pierce': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/e/e3/Paul_Pierce_2008-01-13_%28cropped%29.jpg/1280px-Paul_Pierce_2008-01-13_%28cropped%29.jpg',
  'penny hardaway': 'https://upload.wikimedia.org/wikipedia/commons/2/25/HBCUAllstarBasketball4223-118_%2852802377149%29_%28cropped%29.jpg',
  'pete maravich': 'https://upload.wikimedia.org/wikipedia/commons/2/25/Pete_Maravich_1977.jpeg',
  'ray allen': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/da/Ray_Allen_161208-A-HE359-046_%2831482070191%29.jpg/1280px-Ray_Allen_161208-A-HE359-046_%2831482070191%29.jpg',
  'reggie miller': 'https://upload.wikimedia.org/wikipedia/commons/c/c0/Reggie_Miller_crop.png',
  'rick barry': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/28/Rick_Barry.jpg/1280px-Rick_Barry.jpg',
  'russell westbrook': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/be/Russell_Westbrook_%28March_21%2C_2022%29_%28cropped%29.jpg/1280px-Russell_Westbrook_%28March_21%2C_2022%29_%28cropped%29.jpg',
  'scottie pippen': 'https://upload.wikimedia.org/wikipedia/commons/e/e4/Lipofsky_Pippen.jpg',
  'shai gilgeous-alexander': 'https://upload.wikimedia.org/wikipedia/commons/d/dc/Shai_Gilgeous-Alexander_2024.jpg',
  'shaquille oneal': 'https://upload.wikimedia.org/wikipedia/commons/e/e5/TechCrunch_Disrupt_2023_-_Day_1_%28cropped%29.jpg',
  'stephen curry': 'https://upload.wikimedia.org/wikipedia/commons/8/84/Booker_and_Curry%2C_Paris_2024_Olympic_Games.jpg',
  'steve nash': 'https://upload.wikimedia.org/wikipedia/commons/9/99/SteveNash2014.jpg',
  'tim duncan': 'https://upload.wikimedia.org/wikipedia/commons/c/cb/Tim_Duncan_Walks_Verizon_Center%27s_Floor_%28cropped%29_%28cropped%29.jpg',
  'tim hardaway': 'https://upload.wikimedia.org/wikipedia/commons/2/2b/20150902_Quest_Multisport_clinic_Tim_Hardaway_%281%29.JPG',
  'tony parker': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b8/Tony_Parker_France_20260704_%282%29.jpg/1280px-Tony_Parker_France_20260704_%282%29.jpg',
  'tracy mcgrady': 'https://upload.wikimedia.org/wikipedia/commons/f/f9/Tracy_McGrady_1.jpg',
  'trae young': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/42/Trae_Young_%282022_All-Star_Weekend%29_%28cropped%29.jpg/1280px-Trae_Young_%282022_All-Star_Weekend%29_%28cropped%29.jpg',
  'tyrese haliburton': 'https://upload.wikimedia.org/wikipedia/commons/a/a2/Tyrese_Haliburton_2024.jpg',
  'victor wembanyama': 'https://upload.wikimedia.org/wikipedia/commons/e/ec/Victor_Wembanyama_2024.jpg',
  'vince carter': 'https://upload.wikimedia.org/wikipedia/commons/2/25/Vince_Carter_%28cropped%29.jpg',
  'walt frazier': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/0/07/Walt_Frazier_%28cropped%29.jpg/1280px-Walt_Frazier_%28cropped%29.jpg',
  'willis reed': 'https://upload.wikimedia.org/wikipedia/commons/4/4f/Willis_Reed_1972_publicity_photo.jpg',
  'wilt chamberlain': 'https://upload.wikimedia.org/wikipedia/commons/1/11/Wilt_Chamberlain_1960_%28cropped%29_%28cropped%29.jpg',
  'zion williamson': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/53/Zion_Williamson_2020_%28cropped%29.jpg/1280px-Zion_Williamson_2020_%28cropped%29.jpg'}

NBA_CARD_SPECIFIC_MOMENT_URLS = {}

NBA_HOLO_EDITION_MOMENT_URLS = {}

NBA_2K_MOBILE_CARDS = [ { 'badges': ['HOF 100-Point Game', 'HOF Rebound King', 'HOF Posterizer', 'HOF Anchor', 'HOF Aerial Wizard'],
    'id': 'excl-wilt-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/11/Wilt_Chamberlain_1960_%28cropped%29_%28cropped%29.jpg',
    'moment': "HoldingtheHand- Written• ' • 1 00' •   PaperSigninHersheyArenaLockerRoom •",
    'name': 'Wilt Chamberlain',
    'ovr': 99,
    'pos': 'C',
    'quote': 'Scored100Pointsin• a •   Sing leGame• ( March• 2 • , •   1962) • • •   UnbrokenRecordinSports• H istory '
             '•',
    'sec_pos': 'PF',
    'stats': {'3pt': 55, 'ath': 99, 'clu': 98, 'def': 99, 'ins': 99, 'ply': 85},
    'team': 'PHI',
    'theme': "100- PointGame• ' 100' •   Sign •",
    'tier': 'exclusive'},
  { 'badges': ['HOF Diesel Dominance', 'HOF Dropstepper', 'HOF Backdown Punisher', 'HOF Anchor', 'HOF Posterizer'],
    'id': 'excl-shaq-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/e5/TechCrunch_Disrupt_2023_-_Day_1_%28cropped%29.jpg',
    'moment': '2000WCFGame• 7 •   RunningAll ey- OopLobfromKobevsBl azers •',
    'name': "Shaquille O'Neal",
    'ovr': 99,
    'pos': 'C',
    'quote': '• 3 • - PeatFinalsMVP• • •   2000• M • V • P • • •   MostDominantForceEv er• • •   ShatteringBackboards '
             '• & •   TrophyLifts •',
    'sec_pos': 'PF',
    'stats': {'3pt': 55, 'ath': 99, 'clu': 98, 'def': 98, 'ins': 99, 'ply': 82},
    'team': 'LAL',
    'theme': '• 3 • - PeatFinalsMVP• & •   RimWre cker •',
    'tier': 'exclusive'},
  { 'badges': ['HOF Last Shot', 'HOF Clamps', 'HOF Limitless Takeoff', 'HOF Posterizer', 'HOF Clutch God'],
    'id': 'excl-jordan-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/43/Steve_Lipfosky_--_Michael_Jordan_%281997%29.jpg',
    'moment': "1998FinalsGame• 6 • ' TheLas • t •   Shot' •   OverBryonRussell •   for6thRing •",
    'name': 'Michael Jordan',
    'ovr': 99,
    'pos': 'SG',
    'quote': "6xNBAChampion• • •   6xFinals •   MVP• • •   5xMVP• • •   1998Final • s • ' TheLastShot' •   Historic "
             '•   Farewell •',
    'sec_pos': 'SF',
    'stats': {'3pt': 93, 'ath': 99, 'clu': 99, 'def': 99, 'ins': 99, 'ply': 96},
    'team': 'CHI',
    'theme': "1998Finals• ' TheLastShot' •",
    'tier': 'exclusive'},
  { 'badges': ['HOF Junior Skyhook', 'HOF Showtime Maestro', 'HOF Needle Threader', 'HOF Dimer', 'HOF Floor General'],
    'id': 'excl-magic-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/e8/Pat_Riley_and_Earvin_%22Magic%22_Johnsonat_the_Century_Plaza_%28cropped%29.jpg',
    'moment': "1987FinalsGame• 4 • ' Junior, •   Junior' •   SkyhookGame- Winn eratBostonGarden •",
    'name': 'Magic Johnson',
    'ovr': 99,
    'pos': 'PG',
    'quote': '5xNBAChampion• • •   3xFinals •   MVP• • •   1980Finals42- Pt• G ame• 6 •   asRookieCenter• • • S • h '
             'owtimeMaestro •',
    'sec_pos': 'SF',
    'stats': {'3pt': 86, 'ath': 95, 'clu': 99, 'def': 94, 'ins': 98, 'ply': 99},
    'team': 'LAL',
    'theme': '1980FinalsGame• 6 • & •   Baby• S kyhook •',
    'tier': 'exclusive'},
  { 'badges': ['HOF The Block', 'HOF Chase Down Artist', 'HOF Dimer', 'HOF Bully', 'HOF Floor General'],
    'id': 'excl-lebron-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/2/25/Lebron_wizards_2017_%28cropped%29.jpg',
    'moment': "2016FinalsGame• 7 • ' TheBlo ck' •   onAndreIguodala• & •   Ch ampionshipTears •",
    'name': 'LeBron James',
    'ovr': 99,
    'pos': 'SF',
    'quote': "2016NBAChampion• & •   Finals •   MVP• • • ' Cleveland, •   Thisis •   ForYou! • ' • • •   LegendaryGame "
             '• 7 •   Chase- DownBlock •',
    'sec_pos': 'PF',
    'stats': {'3pt': 91, 'ath': 99, 'clu': 99, 'def': 99, 'ins': 99, 'ply': 99},
    'team': 'CLE',
    'theme': "2016Finals• ' TheBlock' • & • R ing •",
    'tier': 'exclusive'},
  { 'badges': ['HOF 81-Piece', 'HOF Mamba Mentality', 'HOF Deadeye', 'HOF Clamps', 'HOF Difficult Shots'],
    'id': 'excl-kobe-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/43/Kobe_Bryant_Jumper_07_%28cropped%29.jpg',
    'moment': '81- PointHistoricMasterpie cevsRaptors• & •   IndexFing ertotheSky •',
    'name': 'Kobe Bryant',
    'ovr': 99,
    'pos': 'SG',
    'quote': "5xNBAChampion• • •   2xFinals •   MVP• • •   81- PointMasterpiec • e •   vsRaptors• • • ' MambaOut' •   "
             'Farewell •',
    'sec_pos': 'SF',
    'stats': {'3pt': 94, 'ath': 99, 'clu': 99, 'def': 99, 'ins': 99, 'ply': 94},
    'team': 'LAL',
    'theme': '81- PointMasterpiece• & •   Mamb • a •   Out •',
    'tier': 'exclusive'},
  { 'badges': ['HOF Unstoppable Skyhook', 'HOF Post Hook', 'HOF Anchor', 'HOF Dream Shake', 'HOF Dropstepper'],
    'id': 'excl-kareem-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/a/a0/Kareem_Abdul-Jabbar_May_2014.jpg',
    'moment': '1974FinalsGame• 6 •   Iconic• S kyhookBuzzer- BeaterOverBoston •',
    'name': 'Kareem Abdul-Jabbar',
    'ovr': 99,
    'pos': 'C',
    'quote': '6xNBAChampion• • •   6xMVP• • •   19xAll- Star• • •   All- Time• S • c oringKingfor39Years •',
    'sec_pos': 'PF',
    'stats': {'3pt': 60, 'ath': 96, 'clu': 99, 'def': 99, 'ins': 99, 'ply': 88},
    'team': 'LAL',
    'theme': 'UnstoppableSkyhookMaster •',
    'tier': 'exclusive'},
  { 'badges': ['HOF Quadruple Double', 'HOF Post Lock', 'HOF Anchor', 'HOF Rebound Chaser', 'HOF Break Starter'],
    'id': 'excl-duncan-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/cb/Tim_Duncan_Walks_Verizon_Center%27s_Floor_%28cropped%29_%28cropped%29.jpg',
    'moment': '2003FinalsGame• 6 •   21PTS, •   20REB, •   10AST, • 8 •   BLKCham pionshipHug •',
    'name': 'Tim Duncan',
    'ovr': 98,
    'pos': 'PF',
    'quote': '5xNBAChampion• • •   3xFinals •   MVP• • •   2xMVP• • •   2003Final • s •   Quadruple- DoubleChampion '
             'shipGame •',
    'sec_pos': 'C',
    'stats': {'3pt': 68, 'ath': 91, 'clu': 98, 'def': 99, 'ins': 99, 'ply': 89},
    'team': 'NBA',
    'theme': '2003FinalsQuadruple- Doubl • e •',
    'tier': 'exclusive'},
  { 'badges': ['HOF Night Night', 'HOF Limitless Range', 'HOF Chef', 'HOF Agent 3', 'HOF Circus Threes'],
    'id': 'excl-curry-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/8/84/Booker_and_Curry%2C_Paris_2024_Olympic_Games.jpg',
    'moment': "2022FinalsGame• 6 • ' Night• N ight' •   GesturePointingtoRingFinger •",
    'name': 'Stephen Curry',
    'ovr': 98,
    'pos': 'PG',
    'quote': "4xNBAChampion• • •   2022Fina lsMVP• • •   2xMVP• • • ' Night• N ight' •   CelebrationinBoston •   "
             'Garden •',
    'sec_pos': 'SG',
    'stats': {'3pt': 99, 'ath': 94, 'clu': 99, 'def': 88, 'ins': 91, 'ply': 98},
    'team': 'GSW',
    'theme': "2022Finals• ' NightNight' • & •   3PTKing •",
    'tier': 'exclusive'},
  { 'badges': ['HOF Finger In The Air', 'HOF Clutch Shooter', 'HOF Catch & Shoot', 'HOF Deadeye', 'HOF Dimer'],
    'id': 'excl-bird-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/ef/December_1983_One_on_One_Dr_J_vs_Larry_Bird_advertisement_by_Electronic_Arts_%28cropped%29_%28cropped%29.jpg',
    'moment': '19863PTContestLastShot •   FingerintheAirBefore• i • t •   Dropped• & •   JacketOn •',
    'name': 'Larry Bird',
    'ovr': 98,
    'pos': 'SF',
    'quote': "3xNBAChampion• • •   2xFinals •   MVP• • •   3xConsecutiveMVP• • • ' Who' • s •   CominginSecond? • ' "
             '•   3PTLegend •',
    'sec_pos': 'PF',
    'stats': {'3pt': 99, 'ath': 90, 'clu': 99, 'def': 95, 'ins': 95, 'ply': 98},
    'team': 'BOS',
    'theme': '• 3 • - PeatMVP• & •   FingerInThe •   Air •',
    'tier': 'exclusive'},
  { 'badges': ['HOF Finals MVP Dagger', 'HOF Guard Up', 'HOF Deadeye', 'HOF Green Machine', 'HOF Blinders'],
    'id': 'excl-durant-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/4a/Jonas_Maciulis_attacks_the_basket_%28cropped%29.jpg',
    'moment': '2017FinalsGame• 3 •   Cold- Blo odedPull- Up• 3 •   OverLeBron •   James •',
    'name': 'Kevin Durant',
    'ovr': 98,
    'pos': 'SF',
    'quote': '2xNBAChampion• • •   2xFinals •   MVP• • •   2017• & •   2018FinalsGame• 3 •   Pull- UpDaggersOver •   '
             'LeBron •',
    'sec_pos': 'PF',
    'stats': {'3pt': 98, 'ath': 96, 'clu': 99, 'def': 94, 'ins': 98, 'ply': 92},
    'team': 'GSW',
    'theme': 'Back- to- BackFinalsMVPDag gers •',
    'tier': 'exclusive'},
  { 'badges': ['HOF The Dream Shake', 'HOF Post Spin Technician', 'HOF Anchor', 'HOF Post Lock', 'HOF Dropstepper'],
    'id': 'excl-hakeem-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/b/bd/Hakeem.jpg',
    'moment': '1994FinalsDreamShakeCli nicOverPatrickEwing• & • D avidRobinson •',
    'name': 'Hakeem Olajuwon',
    'ovr': 98,
    'pos': 'C',
    'quote': '2xNBAChampion• & •   Finals• M • V • P • • •   1994MVP• & •   DPOYTriple •   Crown• • •   '
             'GreatestFootwork •   inHistory •',
    'sec_pos': 'PF',
    'stats': {'3pt': 65, 'ath': 94, 'clu': 98, 'def': 99, 'ins': 99, 'ply': 85},
    'team': 'HOU',
    'theme': '1994MVP• & •   DreamShakeSwee • p •',
    'tier': 'exclusive'},
  { 'badges': [ 'HOF 11 Rings Anchor',
                'HOF Rim Protector',
                'HOF Rebound Chaser',
                'HOF Post Lock',
                'HOF Fast Break Starter'],
    'id': 'excl-russell-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/d/d3/Bill_russell_dribbling_%28cropped%29.jpg',
    'moment': '1962FinalsGame• 7 •   30Point • s • & •   40ReboundsChampionsh ipClincher •',
    'name': 'Bill Russell',
    'ovr': 98,
    'pos': 'C',
    'quote': '11xNBAChampionin13Seas ons• • •   5xMVP• • •   TheGreates • t •   DefensiveLeader• & •   Winner •   '
             'inHistory •',
    'sec_pos': 'PF',
    'stats': {'3pt': 50, 'ath': 97, 'clu': 99, 'def': 99, 'ins': 96, 'ply': 88},
    'team': 'BOS',
    'theme': '11xChampionGoldStandard •',
    'tier': 'exclusive'},
  { 'badges': ['HOF Triple-Double King', 'HOF Dimer', 'HOF Triple Threat', 'HOF Floor General', 'HOF Break Starter'],
    'id': 'excl-oscar-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/a/a1/Oscar_Robertson_1960.jpeg',
    'moment': '1971FinalsChampionship• C • e lebrationWithKareemin• M ilwaukee •',
    'name': 'Oscar Robertson',
    'ovr': 97,
    'pos': 'PG',
    'quote': '1971NBAChampion• • •   1964• M • V • P • • •   Averaged30. • 8 •   PTS, •   12. • 5 •   REB, •   11. • 4 '
             '•   ASTinSingle• S eason •',
    'sec_pos': 'SG',
    'stats': {'3pt': 86, 'ath': 94, 'clu': 98, 'def': 93, 'ins': 96, 'ply': 99},
    'team': 'MIL',
    'theme': '1971Championship• & •   Triple- DoubleKing •',
    'tier': 'exclusive'},
  { 'badges': [ 'HOF Sombor Shuffle Ring',
                'HOF Needle Threader',
                'HOF Touch Passer',
                'HOF Post Playmaker',
                'HOF Masher'],
    'id': 'excl-jokic-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/7/7e/Nikola_Jokic_free_throw_%28cropped%29.jpg',
    'moment': '2023NBAChampionshipParad • e •   TrophyLift• & •   Celebrator • y •   Laugh •',
    'name': 'Nikola Jokic',
    'ovr': 97,
    'pos': 'C',
    'quote': '2023NBAChampion• & •   Finals •   MVP• • •   3xMVP• • •   Historic• 3 • 0 • - 20- 10FinalsRun• & •   '
             'Sombor •   Shuffle •',
    'sec_pos': 'PF',
    'stats': {'3pt': 91, 'ath': 83, 'clu': 98, 'def': 86, 'ins': 98, 'ply': 99},
    'team': 'DEN',
    'theme': '2023FinalsMVPParade• & • R • i ng •',
    'tier': 'exclusive'},
  { 'badges': ['HOF Anything Is Possible', 'HOF Anchor', 'HOF Post Lock', 'HOF Rebound Chaser', 'HOF Clamps'],
    'id': 'excl-garnett-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/6/60/Kevin_Garnett_2008-01-13.jpg',
    'moment': "2008NBAFinalsGame• 6 •   Conf ettiHug• & • ' ANYTHINGISPO SSIBLE! • ' •   Roar •",
    'name': 'Kevin Garnett',
    'ovr': 97,
    'pos': 'PF',
    'quote': "2008NBAChampion• • •   2004• M • V • P • • •   2008DPOY• • • ' ANYTHINGISPOSSIBLE! • ' •   HistoricPost "
             '• - GameScream •',
    'sec_pos': 'C',
    'stats': {'3pt': 78, 'ath': 96, 'clu': 98, 'def': 99, 'ins': 97, 'ply': 88},
    'team': 'NBA',
    'theme': "• ' ANYTHINGISPOSSIBLE! • ' •   200 • 8 •   Ring •",
    'tier': 'exclusive'},
  { 'badges': ['HOF The Logo 60-Footer', 'HOF Clutch Shooter', 'HOF Deadeye', 'HOF Dimer', 'HOF Middy Magician'],
    'id': 'excl-jerrywest-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/5/5a/Jerry_West_1972.jpeg',
    'moment': '1970FinalsGame• 3 •   60- Foot •   Buzzer- BeatingHalf- Court •   MiracleShot •',
    'name': 'Jerry West',
    'ovr': 97,
    'pos': 'PG',
    'quote': '1972NBAChampion• • •   1969• F • i nalsMVP• ( Onlyonlosing• t eam) • • •   60- FootGame• 3 •   Buzze • r '
             '•   Beater •',
    'sec_pos': 'SG',
    'stats': {'3pt': 96, 'ath': 93, 'clu': 99, 'def': 94, 'ins': 95, 'ply': 97},
    'team': 'LAL',
    'theme': 'TheNBALogo• & •   60- FtBuzzer •   Beater •',
    'tier': 'exclusive'},
  { 'badges': ['HOF 50-Point Clincher', 'HOF Posterizer', 'HOF Bully', 'HOF Anchor', 'HOF Chase Down Artist'],
    'id': 'excl-giannis-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/7/7f/Giannis_Antetokoummpo_%2831669417562%29.jpg',
    'moment': '2021FinalsGame• 6 •   50- Point •   Masterpiece• & •   TrophyKiss •   inMilwaukee •',
    'name': 'Giannis Antetokounmpo',
    'ovr': 97,
    'pos': 'PF',
    'quote': '2021NBAChampion• & •   Finals •   MVP• • •   50Points, •   14Reboun ds, • 5 •   BlocksinGame• 6 •   Cli '
             'ncher •',
    'sec_pos': 'C',
    'stats': {'3pt': 76, 'ath': 99, 'clu': 97, 'def': 99, 'ins': 99, 'ply': 91},
    'team': 'MIL',
    'theme': '2021Finals50- PointMaster piece •',
    'tier': 'exclusive'},
  { 'badges': ['HOF One-Leg Fadeaway', 'HOF Deadeye', 'HOF Catch & Shoot', 'HOF Middy Magician', 'HOF Clutch Shooter'],
    'id': 'excl-dirk-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/5/54/Dirk_Nowitzki_al_rimbalzo.jpg',
    'moment': '2011FinalsGame• 2 •   Left- Han dedGame- WinningDriving• L ayup• & •   TrophyTears •',
    'name': 'Dirk Nowitzki',
    'ovr': 97,
    'pos': 'PF',
    'quote': '2011NBAChampion• & •   Finals •   MVP• • •   2007MVP• • •   Overcomin • g •   MiamiHeatBig• 3 •   WithIc '
             'onicFadeaway •',
    'sec_pos': 'C',
    'stats': {'3pt': 97, 'ath': 84, 'clu': 99, 'def': 84, 'ins': 96, 'ply': 82},
    'team': 'NBA',
    'theme': '2011FinalsGame• 2 •   Fadeaway • & •   Ring •',
    'tier': 'exclusive'},
  { 'badges': ['HOF The Stepover', 'HOF Ankle Breaker', 'HOF Giant Slayer', 'HOF Acrobat', 'HOF Quick First Step'],
    'id': 'excl-iverson-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/f/f4/Allen_Iverson_08_B.jpg',
    'moment': '2001FinalsGame• 1 •   Corner• S tep- BackJumper• & •   Stepover •   OverTyronnLue •',
    'name': 'Allen Iverson',
    'ovr': 97,
    'pos': 'PG',
    'quote': '2001NBAMVP• • •   48- PointGam • e • 1 •   atStaplesCenter• • •   Th • e •   IconicStepoverOverTyro '
             'nnLue •',
    'sec_pos': 'SG',
    'stats': {'3pt': 91, 'ath': 99, 'clu': 99, 'def': 93, 'ins': 97, 'ply': 97},
    'team': 'PHI',
    'theme': '2001FinalsGame• 1 •   TheStep over •',
    'tier': 'exclusive'},
  { 'badges': ['HOF 13 in 33s', 'HOF Limitless Range', 'HOF Posterizer', 'HOF Blindside', 'HOF Deadeye'],
    'id': 'excl-tmac-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/f/f9/Tracy_McGrady_1.jpg',
    'moment': '13Pointsin33SecondsMir acleGame- WinningPull- Up• 3 •   vsSanAntonioSpurs •',
    'name': 'Tracy McGrady',
    'ovr': 96,
    'pos': 'SG',
    'quote': '2xScoringChampion• • •   7x• A • l • l • - Star• • •   Historic13Point • s •   in33SecondsComeback• v • '
             's •   Spurs •',
    'sec_pos': 'SF',
    'stats': {'3pt': 98, 'ath': 97, 'clu': 99, 'def': 91, 'ins': 97, 'ply': 94},
    'team': 'HOU',
    'theme': '13Pointsin33SecondsMir acle •',
    'tier': 'exclusive'},
  { 'badges': ['HOF Ewing Poster Slam', 'HOF Clamps', 'HOF Glove', 'HOF Interceptor', 'HOF Dimer'],
    'id': 'excl-pippen-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/e4/Lipofsky_Pippen.jpg',
    'moment': '1994ECSFGame• 6 •   Tomahawk• P osterSlamOverPatrickEw ing• & •   Strut •',
    'name': 'Scottie Pippen',
    'ovr': 96,
    'pos': 'SF',
    'quote': '6xNBAChampion• • •   7xAll- • S • t ar• • •   8xAll- DefensiveFirs • t •   Team• • •   1994IconicPoster '
             '•   Slam •',
    'sec_pos': 'SG',
    'stats': {'3pt': 88, 'ath': 97, 'clu': 97, 'def': 99, 'ins': 95, 'ply': 94},
    'team': 'CHI',
    'theme': '1994EwingPosterDunk• & • P • o int •',
    'tier': 'exclusive'},
  { 'badges': ['HOF 60-21-10 Miracle', 'HOF Stepback Maestro', 'HOF Dimer', 'HOF Space Creator', 'HOF Ankle Breaker'],
    'id': 'excl-luka-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/b/be/Luka_Don%C4%8Di%C4%87_and_Marines%2C_2026_%28cropped%29.jpg',
    'moment': 'IntentionalMissedFreeThr owPutbackBuzzer- Beater• & •   DancingJigvsKnicks •',
    'name': 'Luka Doncic',
    'ovr': 96,
    'pos': 'PG',
    'quote': '5xAll- NBAFirstTeam• • •   Sco ringChampion• • •   60PTS, •   21 •   REB, •   10ASTMissedFree• T • h '
             'rowPutback •',
    'sec_pos': 'SG',
    'stats': {'3pt': 95, 'ath': 89, 'clu': 99, 'def': 84, 'ins': 97, 'ply': 99},
    'team': 'DAL',
    'theme': '60- 21- 10HistoricPutback• M iracle •',
    'tier': 'exclusive'},
  { 'badges': [ 'HOF 70-Point Masterpiece',
                'HOF Post Spin Technician',
                'HOF Dream Shake',
                'HOF Anchor',
                'HOF Backdown Punisher'],
    'id': 'excl-embiid-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/13/Joel_Embiid_2019.jpg',
    'moment': '70- PointMasterpieceCelebr ation• & •   RoarvsSanAntoni • o •   Spurs •',
    'name': 'Joel Embiid',
    'ovr': 96,
    'pos': 'C',
    'quote': '2023NBAMVP• • •   2xScoring• C hampion• • •   70Points, •   18Re boundsvsSpurs• ( January• 2 • 0 24) •',
    'sec_pos': 'PF',
    'stats': {'3pt': 89, 'ath': 92, 'clu': 97, 'def': 96, 'ins': 99, 'ply': 86},
    'team': 'PHI',
    'theme': '70- PointMasterpiece• & •   MVP •   Flex •',
    'tier': 'exclusive'},
  { 'badges': [ 'HOF 25-Point Sprain',
                'HOF Quick First Step',
                'HOF Handles For Days',
                'HOF Dimer',
                'HOF Clutch Shooter'],
    'id': 'excl-isiah-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/5/50/Isiah-thomas_detroit-v-new-york_1985.jpg',
    'moment': '1988FinalsGame• 6 •   25- Point •   SingleQuarteronHeavily •   SprainedAnkle •',
    'name': 'Isiah Thomas',
    'ovr': 96,
    'pos': 'PG',
    'quote': '2xNBAChampion• • •   1990Fina lsMVP• • •   25Pointsin3rdQuarterof1988Finalson• S evereSprain •',
    'sec_pos': 'SG',
    'stats': {'3pt': 87, 'ath': 95, 'clu': 99, 'def': 94, 'ins': 94, 'ply': 98},
    'team': 'DET',
    'theme': '1988Finals25- PtSprained •   AnkleQuarter •',
    'tier': 'exclusive'},
  { 'badges': ['HOF This Is My House', 'HOF Acrobat', 'HOF Fearless Finisher', 'HOF Clamps', 'HOF Fast Break Starter'],
    'id': 'excl-wade-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/8/88/Dwyane_Wade_2012.jpg',
    'moment': "2006FinalsGame• 3 •   Comeback •   Roar• & •   JumpingonScorer' • s •   Table •",
    'name': 'Dwyane Wade',
    'ovr': 96,
    'pos': 'SG',
    'quote': "3xNBAChampion• • •   2006Fina lsMVP• ( 34. • 7 •   PPGcomebackfrom• 0 • - • 2 • ) • • • ' ThisisMyHou "
             "se! • ' •",
    'sec_pos': 'PG',
    'stats': {'3pt': 84, 'ath': 98, 'clu': 98, 'def': 97, 'ins': 98, 'ply': 95},
    'team': 'MIA',
    'theme': "2006FinalsMVP• & • ' ThisIs •   MyHouse' •",
    'tier': 'exclusive'},
  { 'badges': ['HOF Point God 41-Piece', 'HOF Floor General', 'HOF Dimer', 'HOF Middy Magician', 'HOF Glove'],
    'id': 'excl-cp3-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/a/ad/Chris_Paul_%282022_All-Star_Weekend%29_%28cropped%29.jpg',
    'moment': '2021WCFGame• 6 •   41- Point• S • e condHalfEruptionatStap lesCenter •',
    'name': 'Chris Paul',
    'ovr': 96,
    'pos': 'PG',
    'quote': '12xAll- Star• • •   5xAssists• L eader• • •   6xStealsLeader• • •   41PointsinGame• 6 •   toRea '
             'chNBAFinals •',
    'sec_pos': 'SG',
    'stats': {'3pt': 94, 'ath': 90, 'clu': 98, 'def': 96, 'ins': 89, 'ply': 99},
    'team': 'PHX',
    'theme': '2021WCF41- PointMasterpie ce •',
    'tier': 'exclusive'},
  { 'badges': ['HOF 44-Point Game 7', 'HOF Bully', 'HOF Rebound Chaser', 'HOF Posterizer', 'HOF Fast Twitch'],
    'id': 'excl-barkley-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/f/f6/Charles_Barkley_representing_the_1992_Dream_Team.jpg',
    'moment': '1993WesternConferenceFin alsGame• 7 •   44- Point24- Reb oundRoarvsSonics •',
    'name': 'Charles Barkley',
    'ovr': 96,
    'pos': 'PF',
    'quote': '1993NBAMVP• • •   11xAll- Star • • •   1993WCFGame• 7 •   44PTS, •   24REBMasterclass •',
    'sec_pos': 'SF',
    'stats': {'3pt': 76, 'ath': 97, 'clu': 98, 'def': 92, 'ins': 99, 'ply': 90},
    'team': 'PHX',
    'theme': '1993MVP• & •   44- PtGame• 7 •   Tak eover •',
    'tier': 'exclusive'},
  { 'badges': ['HOF We Did It Ring', 'HOF Clamps', 'HOF Agent 3', 'HOF Catch & Shoot', 'HOF Posterizer'],
    'id': 'excl-tatum-95',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/c8/Jayson_Tatum_Parade_2024.jpg',
    'moment': "2024NBAFinalsGame• 5 •   Clin cher• ' WeDidIt! • ' •   Trophy• S cream• & •   Confetti •",
    'name': 'Jayson Tatum',
    'ovr': 95,
    'pos': 'SF',
    'quote': "2024NBAChampion• • •   3xAll- NBAFirstTeam• • •   Eastern• C onferenceFinalsMVP• • • ' We •   DidIt! • ' "
             '•',
    'sec_pos': 'PF',
    'stats': {'3pt': 96, 'ath': 95, 'clu': 97, 'def': 95, 'ins': 95, 'ply': 91},
    'team': 'BOS',
    'theme': "2024NBAChampionship• ' We• D idIt! • ' •",
    'tier': 'exclusive'},
  { 'badges': [ 'HOF Human Highlight Film',
                'HOF Posterizer',
                'HOF Limitless Takeoff',
                'HOF Aerial Wizard',
                'HOF Fast Twitch'],
    'id': 'excl-wilkins-95',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/4e/Dominique_Wilkins_%2851914585633%29.jpg',
    'moment': '1988SlamDunkContestTwo- HandedBackscratcherWindm illSlam •',
    'name': 'Dominique Wilkins',
    'ovr': 95,
    'pos': 'SF',
    'quote': '2xSlamDunkChampion• • •   198 • 6 •   ScoringChampion• • •   9xAl • l • - Star• • •   TheHumanHighligh • '
             't •   Film •',
    'sec_pos': 'SG',
    'stats': {'3pt': 84, 'ath': 99, 'clu': 96, 'def': 90, 'ins': 98, 'ply': 88},
    'team': 'ATL',
    'theme': '1988DunkContestWindmill •   Duel •',
    'tier': 'exclusive'},
  { 'badges': [ 'HOF Half-Man Half-Amazing',
                'HOF Posterizer',
                'HOF Limitless Takeoff',
                'HOF Aerial Wizard',
                'HOF Acrobat'],
    'id': 'excl-vince-94',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/2/25/Vince_Carter_%28cropped%29.jpg',
    'moment': '2000SlamDunkContestHone • y •   DipElbow- In- The- Rim• & • 3 60WindmillSlam •',
    'name': 'Vince Carter',
    'ovr': 94,
    'pos': 'SG',
    'quote': "2000SlamDunkChampion• • • ' It' • s •   Over! • ' •   Celebration• • •   GreatestDunkContestPerfo "
             'rmanceinHistory •',
    'sec_pos': 'SF',
    'stats': {'3pt': 93, 'ath': 99, 'clu': 96, 'def': 88, 'ins': 99, 'ply': 91},
    'team': 'TOR',
    'theme': '2000DunkContestArm- In- • R • i • m •   GOAT •',
    'tier': 'exclusive'},
  { 'badges': ['HOF Game-Saving Block', 'HOF Anchor', 'HOF Clamps', 'HOF Interceptor', 'HOF Rebound Chaser'],
    'id': 'excl-bam-93',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/f/f0/Adebayo_Hachimura_%28cropped%29.jpg',
    'moment': '2020ECFGame• 1 •   Game- Saving •   Left- HandedRimRejection •   onJaysonTatum •',
    'name': 'Bam Adebayo',
    'ovr': 93,
    'pos': 'C',
    'quote': "3xAll- Star• • •   5xAll- Defens ive• • •   2020EasternConfere nceFinalsGame• 1 •   Blockon •   Tatum' • "
             's •   Dunk •',
    'sec_pos': 'PF',
    'stats': {'3pt': 74, 'ath': 94, 'clu': 96, 'def': 99, 'ins': 94, 'ply': 89},
    'team': 'MIA',
    'theme': '2020ECFGame• 1 •   Game- Saving •   Block •',
    'tier': 'exclusive'},
  { 'badges': ['HOF Posterizer', 'HOF Anchor', 'HOF Dropstepper', 'HOF Backdown Punisher', 'HOF Aerial Wizard'],
    'id': 'dm-wiltchamberlain-99',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/11/Wilt_Chamberlain_1960_%28cropped%29_%28cropped%29.jpg/1280px-Wilt_Chamberlain_1960_%28cropped%29_%28cropped%29.jpg',
    'jersey': 13,
    'name': 'Wilt Chamberlain',
    'ovr': 99,
    'pos': 'C',
    'quote': '2xNBAChampion• • •   4xMVP• • •   Scored100PointsinSingl • e •   Game• • •   ReboundingKing •',
    'sec_pos': 'PF',
    'stats': {'3pt': 55, 'ath': 99, 'clu': 98, 'def': 99, 'ins': 99, 'ply': 85},
    'team': 'PHI',
    'theme': '100- PointDominator •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Anchor', 'HOF Interceptor', 'HOF Limitless Range', 'HOF Rim Protector', 'HOF Pogo Stick'],
    'id': 'dm-wemby-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/ec/Victor_Wembanyama_2024.jpg',
    'jersey': 1,
    'name': 'Victor Wembanyama',
    'ovr': 99,
    'pos': 'C',
    'quote': '7ft4inGenerationalPhenom • • •   NBABlockLeader• • •   Rook ieoftheYearAlien •',
    'sec_pos': 'PF',
    'stats': {'3pt': 92, 'ath': 96, 'clu': 95, 'def': 99, 'ins': 97, 'ply': 88},
    'team': 'SAS',
    'theme': 'AlienInvincible •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Post Lock', 'HOF Anchor', 'HOF Rebound Chaser', 'HOF Dropstepper', 'HOF Break Starter'],
    'id': 'dm-timduncan-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/cb/Tim_Duncan_Walks_Verizon_Center%27s_Floor_%28cropped%29_%28cropped%29.jpg',
    'jersey': 21,
    'name': 'Tim Duncan',
    'ovr': 99,
    'pos': 'PF',
    'quote': '5xNBAChampion• • •   3xFinals •   MVP• • •   2xMVP• • •   Greatest• P owerForwardofAllTime •',
    'sec_pos': 'C',
    'stats': {'3pt': 68, 'ath': 91, 'clu': 98, 'def': 99, 'ins': 99, 'ply': 89},
    'team': 'SAS',
    'theme': 'TheBigFundamental •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Limitless Range', 'HOF Chef', 'HOF Agent 3', 'HOF Handles For Days', 'HOF Circus Threes'],
    'id': 'dm-curry-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/0/07/Stephen_Curry_2022.jpg',
    'jersey': 30,
    'name': 'Stephen Curry',
    'ovr': 99,
    'pos': 'PG',
    'quote': '4xNBAChampion• • •   Finals• M • V • P • • •   2xMVP• ( OnlyUnanimous • ) • • •   GreatestShooterEver •',
    'sec_pos': 'SG',
    'stats': {'3pt': 99, 'ath': 93, 'clu': 99, 'def': 85, 'ins': 89, 'ply': 98},
    'team': 'GSW',
    'theme': 'UnanimousMVP •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Dropstepper', 'HOF Posterizer', 'HOF Rebound Chaser', 'HOF Anchor', 'HOF Backdown Punisher'],
    'id': 'dm-shaq-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/a/a2/Shaq_2007.jpg',
    'jersey': 34,
    'name': "Shaquille O'Neal",
    'ovr': 99,
    'pos': 'C',
    'quote': '4xNBAChampion• • •   3xFinals •   MVP• • •   2000MVP• • •   MostDom inantPhysicalForceinHis tory •',
    'sec_pos': 'PF',
    'stats': {'3pt': 55, 'ath': 98, 'clu': 96, 'def': 97, 'ins': 99, 'ply': 78},
    'team': 'LAL',
    'theme': 'DieselDominance •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Clamps', 'HOF Limitless Takeoff', 'HOF Posterizer', 'HOF Ankle Breaker', 'HOF Clutch Performer'],
    'id': 'dm-jordan-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/43/Steve_Lipfosky_--_Michael_Jordan_%281997%29.jpg',
    'jersey': 23,
    'name': 'Michael Jordan',
    'ovr': 99,
    'pos': 'SG',
    'quote': '6xNBAChampion• • •   6xFinals •   MVP• • •   5xRegularSeason• M VP• • •   TheUndisputedGOAT •',
    'sec_pos': 'SF',
    'stats': {'3pt': 90, 'ath': 99, 'clu': 99, 'def': 99, 'ins': 99, 'ply': 92},
    'team': 'CHI',
    'theme': '• G • . • O • . • A • . • T • . •   Edition •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Needle Threader', 'HOF Dimer', 'HOF Special Delivery', 'HOF Floor General', 'HOF Post Playmaker'],
    'id': 'dm-magic-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/c2/Magic_Johnson_1987.jpg',
    'jersey': 32,
    'name': 'Magic Johnson',
    'ovr': 99,
    'pos': 'PG',
    'quote': '5xNBAChampion• • •   3xFinals •   MVP• • •   3xMVP• • •   LeaderoftheLegendaryShowtimeLake rs •',
    'sec_pos': 'SF',
    'stats': {'3pt': 84, 'ath': 94, 'clu': 98, 'def': 92, 'ins': 96, 'ply': 99},
    'team': 'LAL',
    'theme': 'ShowtimeMaestro •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Chase Down Artist', 'HOF Dimer', 'HOF Bully', 'HOF Fast Twitch', 'HOF Unpluckable'],
    'id': 'dm-lebron-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/7/7a/LeBron_James_%2851959977144%29_%28cropped2%29.jpg',
    'jersey': 23,
    'name': 'LeBron James',
    'ovr': 99,
    'pos': 'SF',
    'quote': '4xNBAChampion• • •   4xFinals •   MVP• • •   All- TimeNBAScorin • g •   Leader• • •   PointForward• M • '
             'a ster •',
    'sec_pos': 'PF',
    'stats': {'3pt': 88, 'ath': 99, 'clu': 98, 'def': 98, 'ins': 99, 'ply': 99},
    'team': 'MIA',
    'theme': 'InvincibleKing •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Clutch Shooter', 'HOF Catch & Shoot', 'HOF Deadeye', 'HOF Dimer', 'HOF Interceptor'],
    'id': 'dm-bird-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/e0/Larry_Bird_Lipofsky.jpg',
    'jersey': 33,
    'name': 'Larry Bird',
    'ovr': 99,
    'pos': 'PF',
    'quote': '3xNBAChampion• • •   2xFinals •   MVP• • •   3xConsecutiveMVP• • •   UltimateCold- BloodedClu tchShooter '
             '•',
    'sec_pos': 'SF',
    'stats': {'3pt': 98, 'ath': 89, 'clu': 99, 'def': 94, 'ins': 94, 'ply': 97},
    'team': 'BOS',
    'theme': 'BostonLegend •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Mamba Mentality', 'HOF Blinders', 'HOF Deadeye', 'HOF Clamps', 'HOF Difficult Shots'],
    'id': 'dm-kobe-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/43/Kobe_Bryant_Jumper_07_%28cropped%29.jpg',
    'jersey': 24,
    'name': 'Kobe Bryant',
    'ovr': 99,
    'pos': 'SG',
    'quote': '5xNBAChampion• • •   2xFinals •   MVP• • •   18xAll- Star• • •   Rele ntlessMambaMentality •',
    'sec_pos': 'SF',
    'stats': {'3pt': 92, 'ath': 98, 'clu': 99, 'def': 98, 'ins': 98, 'ply': 90},
    'team': 'LAL',
    'theme': '81- PtMasterpiece •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Guard Up', 'HOF Deadeye', 'HOF Green Machine', 'HOF Blinders', 'HOF Slippery Off-Ball'],
    'id': 'dm-kd-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/2/23/Kevin_Durant_2022.jpg',
    'jersey': 35,
    'name': 'Kevin Durant',
    'ovr': 99,
    'pos': 'SF',
    'quote': '2xNBAChampion• • •   2xFinals •   MVP• • •   2014MVP• • •   Unblocka ble7ft• 3 • - LevelScoringMac hine '
             '•',
    'sec_pos': 'PF',
    'stats': {'3pt': 98, 'ath': 96, 'clu': 99, 'def': 93, 'ins': 97, 'ply': 90},
    'team': 'GSW',
    'theme': 'SlimReaper• 3 • - Level •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Post Spin Technician', 'HOF Anchor', 'HOF Post Hook', 'HOF Dream Shake', 'HOF Dropstepper'],
    'id': 'dm-kareemabduljabbar-99',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a0/Kareem_Abdul-Jabbar_May_2014.jpg/1280px-Kareem_Abdul-Jabbar_May_2014.jpg',
    'jersey': 33,
    'name': 'Kareem Abdul-Jabbar',
    'ovr': 99,
    'pos': 'C',
    'quote': '6xNBAChampion• • •   6xMVP• • •   19xAll- Star• • •   Unstoppable •   SkyhookMaster •',
    'sec_pos': 'PF',
    'stats': {'3pt': 58, 'ath': 95, 'clu': 99, 'def': 98, 'ins': 99, 'ply': 89},
    'team': 'LAL',
    'theme': 'SkyhookMaster •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Post Spin Technician', 'HOF Anchor', 'HOF Dream Shake', 'HOF Post Lock', 'HOF Dropstepper'],
    'id': 'dm-hakeemolajuwon-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/8/84/Nigerian_President_Buhari_Stands_With_Secretary_Kerry%2C_U.S._Delegation_After_They_Attended_His_Inauguration_Ceremony_%28cropped%29.jpg',
    'jersey': 34,
    'name': 'Hakeem Olajuwon',
    'ovr': 99,
    'pos': 'C',
    'quote': '2xNBAChampion• • •   2xFinals •   MVP• • •   1994MVP• • •   All- Time •   NBABlocksLeader •',
    'sec_pos': 'PF',
    'stats': {'3pt': 65, 'ath': 94, 'clu': 98, 'def': 99, 'ins': 99, 'ply': 85},
    'team': 'HOU',
    'theme': 'TheDreamShake •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Posterizer', 'HOF Bully', 'HOF Anchor', 'HOF Chase Down Artist', 'HOF Fast Twitch'],
    'id': 'dm-giannis-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/4d/Giannis_Antetokounmpo_2021.jpg',
    'jersey': 34,
    'name': 'Giannis Antetokounmpo',
    'ovr': 99,
    'pos': 'PF',
    'quote': '2021NBAChampion• & •   Finals •   MVP• • •   2xMVP• • •   2020DPOY• • •   UnstoppableEuro- StepMon ster '
             '•',
    'sec_pos': 'C',
    'stats': {'3pt': 75, 'ath': 99, 'clu': 96, 'def': 99, 'ins': 99, 'ply': 90},
    'team': 'MIL',
    'theme': 'GreekFreakMVP •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Anchor', 'HOF Rim Protector', 'HOF Rebound Chaser', 'HOF Post Lock', 'HOF Fast Break Starter'],
    'id': 'dm-billrussell-99',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/d/d3/Bill_russell_dribbling_%28cropped%29.jpg',
    'jersey': 6,
    'name': 'Bill Russell',
    'ovr': 99,
    'pos': 'C',
    'quote': '11xNBAChampion• • •   5xMVP• • •   UltimateDefensiveAnchor •   andWinningIcon •',
    'sec_pos': 'PF',
    'stats': {'3pt': 50, 'ath': 96, 'clu': 98, 'def': 99, 'ins': 94, 'ply': 86},
    'team': 'BOS',
    'theme': '11xChampionAnchor •',
    'tier': 'dark_matter'},
  { 'badges': ['HOF Glove', 'HOF Dimer', 'HOF Clamps', 'HOF Floor General'],
    'id': 'go-waltfrazier-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/0/07/Walt_Frazier_%28cropped%29.jpg/1280px-Walt_Frazier_%28cropped%29.jpg',
    'jersey': 10,
    'name': 'Walt Frazier',
    'ovr': 98,
    'pos': 'PG',
    'quote': '2xNBAChampion• • •   7xAll- • S • t ar• • •   1970Game• 7 •   36PTS• & •   19ASTMasterpiece •',
    'sec_pos': 'SG',
    'stats': {'3pt': 99, 'ath': 99, 'clu': 99, 'def': 95, 'ins': 94, 'ply': 99},
    'team': 'NYK',
    'theme': 'Clyde1970Finals36- 19 •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Limitless Range', 'HOF Posterizer', 'HOF Blindside', 'HOF Deadeye'],
    'id': 'go-tmac-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/3/33/Alex_Caruso_%2852480104636%29_%28cropped%29.jpg',
    'jersey': 23,
    'name': 'Tracy McGrady',
    'ovr': 98,
    'pos': 'SG',
    'quote': '2xScoringChampion• • •   7x• A • l • l • - Star• • •   Scored13Pointsin35SecondsinHistoric• C omeback •',
    'sec_pos': 'SF',
    'stats': {'3pt': 97, 'ath': 97, 'clu': 99, 'def': 90, 'ins': 97, 'ply': 94},
    'team': 'ORL',
    'theme': '13in35s •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Dimer', 'HOF Needle Threader', 'HOF Catch & Shoot', 'HOF Handles For Days'],
    'id': 'go-stevenash-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/9/99/SteveNash2014.jpg',
    'jersey': 13,
    'name': 'Steve Nash',
    'ovr': 98,
    'pos': 'PG',
    'quote': '2xRegularSeasonMVP• • •   8x •   All- Star• • •   5xNBAAssists •   Leader• • •   50- 40- 90Master •',
    'sec_pos': 'SG',
    'stats': {'3pt': 95, 'ath': 90, 'clu': 96, 'def': 78, 'ins': 84, 'ply': 99},
    'team': 'PHX',
    'theme': '• 7 •   SecondsorLessMVP •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Glove', 'HOF Interceptor', 'HOF Dimer'],
    'id': 'go-scottiepippen-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/5f/Scottie_Pippen_5-2-22_%28cropped%29.jpg/1280px-Scottie_Pippen_5-2-22_%28cropped%29.jpg',
    'jersey': 33,
    'name': 'Scottie Pippen',
    'ovr': 98,
    'pos': 'SF',
    'quote': '6xNBAChampion• • •   7xAll- • S • t ar• • •   8xAll- DefensiveFirs • t •   TeamAnchor •',
    'sec_pos': 'SG',
    'stats': {'3pt': 93, 'ath': 97, 'clu': 99, 'def': 99, 'ins': 99, 'ply': 97},
    'team': 'CHI',
    'theme': '6xChampionLockdown •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Anchor', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-paulgeorge-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/71/1_paul_george_2026_%28cropped%29.jpg/1280px-1_paul_george_2026_%28cropped%29.jpg',
    'jersey': 13,
    'name': 'Paul George',
    'ovr': 98,
    'pos': 'C',
    'quote': 'HallofFameLegend• • •   9x• N • B • A •   All- Star• ( 2013– 2014; •   201 • 6 • – 2019; •   2021; •   '
             '2023– 2024) • • •   Era- DefiningSuperstar •',
    'sec_pos': 'PG',
    'stats': {'3pt': 77, 'ath': 99, 'clu': 99, 'def': 99, 'ins': 99, 'ply': 89},
    'team': 'DEN',
    'theme': 'HallofFameLegend• ( 9xAll • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Anchor', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-patrickewing-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/0/05/Patrick_Ewing_2021_%28cropped%29.jpg/1280px-Patrick_Ewing_2021_%28cropped%29.jpg',
    'jersey': 33,
    'name': 'Patrick Ewing',
    'ovr': 98,
    'pos': 'C',
    'quote': 'HallofFameLegend• • •   11x• N BAAll- Star• ( 1986; •   1988– 19 97) • • •   Era- DefiningSupersta • r •',
    'sec_pos': 'SG',
    'stats': {'3pt': 78, 'ath': 99, 'clu': 94, 'def': 99, 'ins': 99, 'ply': 90},
    'team': 'CHA',
    'theme': 'HallofFameLegend• ( 11x• A • l • l • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Dimer', 'HOF Triple Threat', 'HOF Floor General', 'HOF Break Starter'],
    'id': 'go-oscarrobertson-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/de/Oscar_Robertson_2024.jpg/1280px-Oscar_Robertson_2024.jpg',
    'jersey': 1,
    'name': 'Oscar Robertson',
    'ovr': 98,
    'pos': 'PG',
    'quote': '1971NBAChampion• • •   1964• M • V • P • • •   FirstPlayertoAverag • e • a •   Triple- Double •',
    'sec_pos': 'SG',
    'stats': {'3pt': 95, 'ath': 99, 'clu': 98, 'def': 92, 'ins': 93, 'ply': 98},
    'team': 'MIL',
    'theme': 'TheBig• O •   Triple- Double •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Needle Threader', 'HOF Touch Passer', 'HOF Post Playmaker', 'HOF Masher'],
    'id': 'go-jokic-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/8/87/Nikola_Jokic_2023.jpg',
    'jersey': 15,
    'name': 'Nikola Jokic',
    'ovr': 98,
    'pos': 'C',
    'quote': '2023NBAChampion• & •   Finals •   MVP• • •   3xMVP• • •   Greatest• P • a ssingBigManinHistory •',
    'sec_pos': 'PF',
    'stats': {'3pt': 90, 'ath': 82, 'clu': 98, 'def': 85, 'ins': 98, 'ply': 99},
    'team': 'DEN',
    'theme': 'PointCenterGenius •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Rebound Chaser', 'HOF Boxout Beast', 'HOF Putback Boss', 'HOF Dropstepper'],
    'id': 'go-mosesmalone-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/a/a1/Moses_Malone_cropped_portrait.jpg',
    'jersey': 2,
    'name': 'Moses Malone',
    'ovr': 98,
    'pos': 'C',
    'quote': '1983NBAChampion• & •   Finals •   MVP• • •   3xMVP• • •   12xAll- Sta • r •',
    'sec_pos': 'PF',
    'stats': {'3pt': 73, 'ath': 99, 'clu': 95, 'def': 99, 'ins': 99, 'ply': 91},
    'team': 'PHI',
    'theme': 'ChairmanoftheBoards •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Stepback Maestro', 'HOF Dimer', 'HOF Space Creator', 'HOF Ankle Breaker'],
    'id': 'go-luka-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/ce/Luka_Doncic_2021.jpg',
    'jersey': 77,
    'name': 'Luka Doncic',
    'ovr': 98,
    'pos': 'PG',
    'quote': '5xAll- NBAFirstTeam• • •   Sco ringChampion• • •   MasteroftheUnstoppableStep- Back• T hree •',
    'sec_pos': 'SG',
    'stats': {'3pt': 94, 'ath': 88, 'clu': 98, 'def': 84, 'ins': 96, 'ply': 99},
    'team': 'DAL',
    'theme': 'TripleDoubleKing •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-kyrieirving-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/27/Kyrie_Irving_%2851830909437%29_%28cropped%29.jpg/1280px-Kyrie_Irving_%2851830909437%29_%28cropped%29.jpg',
    'jersey': 11,
    'name': 'Kyrie Irving',
    'ovr': 98,
    'pos': 'PF',
    'quote': 'HallofFameLegend• • •   9x• N • B • A •   All- Star• ( 2013– 2015; •   201 • 7 • – 2019; •   2021; •   '
             '2023; •   2025) • • •   Era- DefiningSuperstar •',
    'sec_pos': 'PG',
    'stats': {'3pt': 86, 'ath': 96, 'clu': 94, 'def': 97, 'ins': 99, 'ply': 89},
    'team': 'DAL',
    'theme': 'HallofFameLegend• ( 9xAll • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Anchor', 'HOF Post Lock', 'HOF Rebound Chaser', 'HOF Clamps'],
    'id': 'go-kevingarnett-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/6/60/Kevin_Garnett_2008-01-13.jpg/1280px-Kevin_Garnett_2008-01-13.jpg',
    'jersey': 21,
    'name': 'Kevin Garnett',
    'ovr': 98,
    'pos': 'PF',
    'quote': '2008NBAChampion• • •   2004• M • V • P • • •   2008DPOY• • •   15xAll- St ar •',
    'sec_pos': 'C',
    'stats': {'3pt': 85, 'ath': 99, 'clu': 99, 'def': 99, 'ins': 99, 'ply': 94},
    'team': 'BOS',
    'theme': 'TheBigTicket •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Backdown Punisher', 'HOF Dropstepper', 'HOF Post Lock', 'HOF Rebound Chaser'],
    'id': 'go-karlmalone-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/e5/NBA_HOF%E2%80%99er_Karl_Malone_visits_Barksdale_%289%29_%28cropped%29.jpg',
    'jersey': 32,
    'name': 'Karl Malone',
    'ovr': 98,
    'pos': 'PF',
    'quote': '2xMVP• • •   14xAll- Star• • •   Ove • r •   36, 000CareerPoints• • • 1 1xAll- NBAFirstTeam •',
    'sec_pos': 'C',
    'stats': {'3pt': 83, 'ath': 99, 'clu': 94, 'def': 99, 'ins': 99, 'ply': 91},
    'team': 'UTA',
    'theme': 'TheMailmanPick• & •   Roll •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Posterizer', 'HOF Limitless Takeoff', 'HOF Acrobat', 'HOF Aerial Wizard'],
    'id': 'go-juliuserving-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/0/0d/Julius_Erving_2016.jpg',
    'jersey': 7,
    'name': 'Julius Erving',
    'ovr': 98,
    'pos': 'SF',
    'quote': '1983NBAChampion• • •   1981• M • V • P • • •   11xNBAAll- Star• • •   Cra dleDunkLegend •',
    'sec_pos': 'SG',
    'stats': {'3pt': 96, 'ath': 96, 'clu': 95, 'def': 99, 'ins': 99, 'ply': 97},
    'team': 'PHI',
    'theme': 'Dr. • J •   AbovetheRim •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Needle Threader', 'HOF Dimer', 'HOF Glove', 'HOF Floor General'],
    'id': 'go-johnstockton-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/cf/John_Stockton_2022.jpg',
    'jersey': 12,
    'name': 'John Stockton',
    'ovr': 98,
    'pos': 'PG',
    'quote': 'All- TimeNBAAssists• & •   Stea lsLeader• • •   10xAll- Star• • •   FloorGeneralLegend •',
    'sec_pos': 'SG',
    'stats': {'3pt': 90, 'ath': 91, 'clu': 95, 'def': 96, 'ins': 86, 'ply': 99},
    'team': 'UTA',
    'theme': 'All- TimeAssistKing •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Post Spin Technician', 'HOF Dream Shake', 'HOF Anchor', 'HOF Backdown Punisher'],
    'id': 'go-embiid-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/1e/Joel_Embiid_2022.jpg',
    'jersey': 21,
    'name': 'Joel Embiid',
    'ovr': 98,
    'pos': 'C',
    'quote': '2023NBAMVP• • •   2xScoring• C hampion• • •   70- PointGameLe gend •',
    'sec_pos': 'PF',
    'stats': {'3pt': 88, 'ath': 90, 'clu': 96, 'def': 96, 'ins': 99, 'ply': 84},
    'team': 'PHI',
    'theme': 'ProcessMVP •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clutch Shooter', 'HOF Deadeye', 'HOF Dimer', 'HOF Middy Magician'],
    'id': 'go-jerrywest-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/5a/Jerry_West_1972.jpeg/1280px-Jerry_West_1972.jpeg',
    'jersey': 44,
    'name': 'Jerry West',
    'ovr': 98,
    'pos': 'PG',
    'quote': '1972NBAChampion• • •   1969• F • i nalsMVP• • •   14xAll- Star• • •   TheIconicNBASilhouette •',
    'sec_pos': 'SG',
    'stats': {'3pt': 96, 'ath': 99, 'clu': 97, 'def': 95, 'ins': 95, 'ply': 99},
    'team': 'LAL',
    'theme': 'TheNBALogo •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Agent 3', 'HOF Catch & Shoot', 'HOF Posterizer'],
    'id': 'go-tatum-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/c8/Jayson_Tatum_Parade_2024.jpg',
    'jersey': 0,
    'name': 'Jayson Tatum',
    'ovr': 98,
    'pos': 'SF',
    'quote': '2024NBAChampion• • •   3xAll- NBAFirstTeam• • •   Eastern• C onferenceFinalsMVP •',
    'sec_pos': 'PF',
    'stats': {'3pt': 95, 'ath': 94, 'clu': 96, 'def': 95, 'ins': 95, 'ply': 90},
    'team': 'BOS',
    'theme': 'FinalsChampion •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Floor General', 'HOF Break Starter', 'HOF Glove', 'HOF Needle Threader'],
    'id': 'go-jasonkidd-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/8/84/Jason_Kidd_Nets_coach_cropped.jpg',
    'jersey': 5,
    'name': 'Jason Kidd',
    'ovr': 98,
    'pos': 'PG',
    'quote': '2011NBAChampion• • •   10xAll • - Star• • •   2ndAll- TimeinNB • A •   Assists• & •   Steals •',
    'sec_pos': 'SG',
    'stats': {'3pt': 84, 'ath': 93, 'clu': 94, 'def': 97, 'ins': 86, 'ply': 98},
    'team': 'NJN',
    'theme': 'Triple- DoubleGeneral •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Quick First Step', 'HOF Handles For Days', 'HOF Dimer', 'HOF Clutch Shooter'],
    'id': 'go-isiahthomas-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/1e/Isiah_Thomas_2007_%28cropped%29.jpg',
    'jersey': 11,
    'name': 'Isiah Thomas',
    'ovr': 98,
    'pos': 'PG',
    'quote': '2xNBAChampion• • •   1990Fina lsMVP• • •   12xAll- Star• • •   25 • - PtSprainedAnkleQuarter •',
    'sec_pos': 'SG',
    'stats': {'3pt': 95, 'ath': 97, 'clu': 93, 'def': 95, 'ins': 93, 'ply': 99},
    'team': 'DET',
    'theme': 'BadBoysGeneral •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Acrobat', 'HOF Aerial Wizard', 'HOF Middy Magician', 'HOF Fearless Finisher'],
    'id': 'go-elginbaylor-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/e5/Elgin_Baylor_Night_program-%28cropped%29.jpg',
    'jersey': 63,
    'name': 'Elgin Baylor',
    'ovr': 98,
    'pos': 'SF',
    'quote': '11xAll- Star• • •   10xAll- NBA •   FirstTeam• • •   61- PointNBA •   FinalsGameRecord •',
    'sec_pos': 'PF',
    'stats': {'3pt': 98, 'ath': 99, 'clu': 99, 'def': 98, 'ins': 98, 'ply': 95},
    'team': 'LAL',
    'theme': 'AcrobaticPioneer •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Acrobat', 'HOF Fearless Finisher', 'HOF Clamps', 'HOF Fast Break Starter'],
    'id': 'go-dwyanewade-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/73/Dwyane_Wade_e1.jpg/1280px-Dwyane_Wade_e1.jpg',
    'jersey': 3,
    'name': 'Dwyane Wade',
    'ovr': 98,
    'pos': 'SG',
    'quote': '3xNBAChampion• • •   2006Fina lsMVP• • •   13xAll- Star• • •   Mi amiHeatIcon •',
    'sec_pos': 'PG',
    'stats': {'3pt': 98, 'ath': 99, 'clu': 98, 'def': 93, 'ins': 99, 'ply': 95},
    'team': 'MIA',
    'theme': 'FlashFinalsMVP •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-dominiquewilkins-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/76/Dominique_Wilkins_2022.jpg/1280px-Dominique_Wilkins_2022.jpg',
    'jersey': 21,
    'name': 'Dominique Wilkins',
    'ovr': 98,
    'pos': 'SG',
    'quote': 'HallofFameLegend• • •   9x• N • B • A •   All- Star• ( 1986– 1994) • • • E ra- DefiningSuperstar •',
    'sec_pos': 'C',
    'stats': {'3pt': 99, 'ath': 99, 'clu': 98, 'def': 95, 'ins': 99, 'ply': 98},
    'team': 'ATL',
    'theme': 'HallofFameLegend• ( 9xAll • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Deadeye', 'HOF Catch & Shoot', 'HOF Middy Magician', 'HOF Clutch Shooter'],
    'id': 'go-dirknowitzki-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/1d/Dirk_Nowitzki_2_%28cropped%29.jpg/1280px-Dirk_Nowitzki_2_%28cropped%29.jpg',
    'jersey': 41,
    'name': 'Dirk Nowitzki',
    'ovr': 98,
    'pos': 'PF',
    'quote': '2011NBAChampion• & •   Finals •   MVP• • •   2007MVP• • •   14xAll- • S tar• • •   31KPoints •',
    'sec_pos': 'C',
    'stats': {'3pt': 86, 'ath': 99, 'clu': 97, 'def': 99, 'ins': 98, 'ply': 92},
    'team': 'DAL',
    'theme': 'One- LegFadeawayRing •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Anchor', 'HOF Rim Protector', 'HOF Post Lock', 'HOF Chase Down Artist'],
    'id': 'go-davidrobinson-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/c9/David_Robinson_%28Team_USA%29.jpg',
    'jersey': 50,
    'name': 'David Robinson',
    'ovr': 98,
    'pos': 'C',
    'quote': '2xNBAChampion• • •   1995MVP • • •   1992DPOY• • •   Quadruple- • D • o ubleLegend •',
    'sec_pos': 'PF',
    'stats': {'3pt': 73, 'ath': 99, 'clu': 96, 'def': 99, 'ins': 99, 'ply': 85},
    'team': 'SAS',
    'theme': 'TheAdmiralQuadruple- Doubl • e •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-damianlillard-98',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/8/8e/Damian_Lillard_%282021%29_%28cropped%29.jpg/1280px-Damian_Lillard_%282021%29_%28cropped%29.jpg',
    'jersey': 0,
    'name': 'Damian Lillard',
    'ovr': 98,
    'pos': 'SG',
    'quote': 'HallofFameLegend• • •   9x• N • B • A •   All- Star• ( 2014– 2015; •   201 • 8 • – 2021; •   2023– 2025) '
             '• • •   Era- • D • e finingSuperstar •',
    'sec_pos': 'C',
    'stats': {'3pt': 96, 'ath': 93, 'clu': 98, 'def': 82, 'ins': 92, 'ply': 93},
    'team': 'MIL',
    'theme': 'HallofFameLegend• ( 9xAll • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-clydedrexler-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/6/62/Clyde_Drexler_01.jpg',
    'jersey': 22,
    'name': 'Clyde Drexler',
    'ovr': 98,
    'pos': 'PF',
    'quote': 'HallofFameLegend• • •   10x• N BAAll- Star• ( 1986; •   1988– 19 94; •   1996– 1997) • • •   Era- Defini '
             'ngSuperstar •',
    'sec_pos': 'SG',
    'stats': {'3pt': 84, 'ath': 98, 'clu': 96, 'def': 99, 'ins': 99, 'ply': 88},
    'team': 'GSW',
    'theme': 'HallofFameLegend• ( 10x• A • l • l • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Bully', 'HOF Rebound Chaser', 'HOF Posterizer', 'HOF Fast Twitch'],
    'id': 'go-charlesbarkley-98',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/3/3c/Charles_Barkley_in_2026.jpg',
    'jersey': 34,
    'name': 'Charles Barkley',
    'ovr': 98,
    'pos': 'PF',
    'quote': '1993MVP• • •   11xAll- Star• • • U nstoppablePowerForward• F orce •',
    'sec_pos': 'SF',
    'stats': {'3pt': 81, 'ath': 97, 'clu': 99, 'def': 99, 'ins': 99, 'ply': 88},
    'team': 'PHX',
    'theme': 'RoundMoundofRebound •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-willisreed-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/4f/Willis_Reed_1972_publicity_photo.jpg',
    'jersey': 19,
    'name': 'Willis Reed',
    'ovr': 97,
    'pos': 'SG',
    'quote': 'HallofFameLegend• • •   7x• N • B • A •   All- Star• ( 1965– 1971) • • • E ra- DefiningSuperstar •',
    'sec_pos': 'SF',
    'stats': {'3pt': 97, 'ath': 99, 'clu': 99, 'def': 91, 'ins': 94, 'ply': 95},
    'team': 'WAS',
    'theme': 'HallofFameLegend• ( 7xAll • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Posterizer', 'HOF Limitless Takeoff', 'HOF Aerial Wizard', 'HOF Acrobat'],
    'id': 'go-vincecarter-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/9/93/Vince_Carter_2013-03-25_%281%29.jpg',
    'jersey': 15,
    'name': 'Vince Carter',
    'ovr': 97,
    'pos': 'SG',
    'quote': '8xAll- Star• • •   2000DunkCon testGOAT• • •   22NBASeasons •   Legend •',
    'sec_pos': 'SF',
    'stats': {'3pt': 92, 'ath': 98, 'clu': 95, 'def': 87, 'ins': 98, 'ply': 90},
    'team': 'TOR',
    'theme': 'Half- ManHalf- Amazing •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Giant Slayer', 'HOF Quick First Step', 'HOF Acrobat', 'HOF Middy Magician'],
    'id': 'go-tonyparker-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b8/Tony_Parker_France_20260704_%282%29.jpg/1280px-Tony_Parker_France_20260704_%282%29.jpg',
    'jersey': 9,
    'name': 'Tony Parker',
    'ovr': 97,
    'pos': 'PG',
    'quote': '4xNBAChampion• • •   2007Fina lsMVP• • •   6xAll- Star• • •   Tea rdropFloaterKing •',
    'sec_pos': 'SG',
    'stats': {'3pt': 97, 'ath': 99, 'clu': 98, 'def': 95, 'ins': 90, 'ply': 96},
    'team': 'SAS',
    'theme': '2007FinalsMVPTeardrop •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-timhardaway-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/2/2b/20150902_Quest_Multisport_clinic_Tim_Hardaway_%281%29.JPG',
    'jersey': 10,
    'name': 'Tim Hardaway',
    'ovr': 97,
    'pos': 'PF',
    'quote': 'HallofFameLegend• • •   5x• N • B • A •   All- Star• ( 1991– 1993; •   199 • 7 • – 1998) • • •   Era- '
             'DefiningSupe rstar •',
    'sec_pos': 'PG',
    'stats': {'3pt': 83, 'ath': 98, 'clu': 94, 'def': 99, 'ins': 99, 'ply': 90},
    'team': 'MIN',
    'theme': 'HallofFameLegend• ( 5xAll • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Fast Twitch', 'HOF Posterizer', 'HOF Break Starter', 'HOF Bully'],
    'id': 'go-russellwestbrook-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/be/Russell_Westbrook_%28March_21%2C_2022%29_%28cropped%29.jpg/1280px-Russell_Westbrook_%28March_21%2C_2022%29_%28cropped%29.jpg',
    'jersey': 0,
    'name': 'Russell Westbrook',
    'ovr': 97,
    'pos': 'PG',
    'quote': '2017NBAMVP• • •   9xAll- Star • • •   All- TimeNBATriple- Doub leRecordLeader •',
    'sec_pos': 'SG',
    'stats': {'3pt': 98, 'ath': 99, 'clu': 97, 'def': 95, 'ins': 91, 'ply': 98},
    'team': 'OKC',
    'theme': 'Triple- DoubleSeasonMVP •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-rickbarry-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/28/Rick_Barry.jpg/1280px-Rick_Barry.jpg',
    'jersey': 24,
    'name': 'Rick Barry',
    'ovr': 97,
    'pos': 'SF',
    'quote': 'HallofFameLegend• • •   8x• N • B • A •   All- Star• ( 1966– 1967; •   197 • 3 • – 1978) • • •   Era- '
             'DefiningSupe rstar •',
    'sec_pos': 'PF',
    'stats': {'3pt': 92, 'ath': 97, 'clu': 96, 'def': 99, 'ins': 99, 'ply': 97},
    'team': 'ATL',
    'theme': 'HallofFameLegend• ( 8xAll • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Limitless Range', 'HOF Catch & Shoot', 'HOF Clutch Shooter', 'HOF Deadeye'],
    'id': 'go-reggiemiller-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/c0/Reggie_Miller_crop.png',
    'jersey': 31,
    'name': 'Reggie Miller',
    'ovr': 97,
    'pos': 'SG',
    'quote': '5xAll- Star• • • 3 • - PointPione er• • •   LegendaryMSGPlayoff •   Heartbreaker •',
    'sec_pos': 'SF',
    'stats': {'3pt': 96, 'ath': 89, 'clu': 98, 'def': 85, 'ins': 87, 'ply': 84},
    'team': 'IND',
    'theme': '• 8 •   Pointsin• 9 •   Seconds •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Corner Specialist', 'HOF Catch & Shoot', 'HOF Limitless Range', 'HOF Clutch Shooter'],
    'id': 'go-rayallen-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/da/Ray_Allen_161208-A-HE359-046_%2831482070191%29.jpg/1280px-Ray_Allen_161208-A-HE359-046_%2831482070191%29.jpg',
    'jersey': 20,
    'name': 'Ray Allen',
    'ovr': 97,
    'pos': 'SG',
    'quote': '2xNBAChampion• • •   10xAll- • S tar• • •   Legendary2013Final • s •   Game• 6 •   Tie• 3 •',
    'sec_pos': 'SF',
    'stats': {'3pt': 97, 'ath': 91, 'clu': 97, 'def': 86, 'ins': 88, 'ply': 87},
    'team': 'MIA',
    'theme': 'Game• 6 •   CornerMiracle •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-petemaravich-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/2/25/Pete_Maravich_1977.jpeg',
    'jersey': 7,
    'name': 'Pete Maravich',
    'ovr': 97,
    'pos': 'SF',
    'quote': 'HallofFameLegend• • •   5x• N • B • A •   All- Star• ( 1973– 1974; •   197 • 7 • – 1979) • • •   Era- '
             'DefiningSupe rstar •',
    'sec_pos': 'SG',
    'stats': {'3pt': 92, 'ath': 99, 'clu': 94, 'def': 95, 'ins': 99, 'ply': 96},
    'team': 'GSW',
    'theme': 'HallofFameLegend• ( 5xAll • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clutch Shooter', 'HOF Middy Magician', 'HOF Deadeye', 'HOF Difficult Shots'],
    'id': 'go-paulpierce-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/e/e3/Paul_Pierce_2008-01-13_%28cropped%29.jpg/1280px-Paul_Pierce_2008-01-13_%28cropped%29.jpg',
    'jersey': 34,
    'name': 'Paul Pierce',
    'ovr': 97,
    'pos': 'SF',
    'quote': '2008NBAChampion• & •   Finals •   MVP• • •   10xAll- Star• • •   Cold- BloodedClutchScorer •',
    'sec_pos': 'SG',
    'stats': {'3pt': 95, 'ath': 97, 'clu': 98, 'def': 95, 'ins': 97, 'ply': 92},
    'team': 'BOS',
    'theme': 'TheTruthFinalsMVP •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Glove', 'HOF Clamps', 'HOF Interceptor', 'HOF Middy Magician'],
    'id': 'go-kawhi-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/5/5a/Kawhi_Leonard_2019.jpg',
    'jersey': 2,
    'name': 'Kawhi Leonard',
    'ovr': 97,
    'pos': 'SF',
    'quote': '2xNBAChampion• • •   2xFinals •   MVP• • •   2xDPOY• • •   TheBuzze • r • - BeatingCornerJumper •',
    'sec_pos': 'SG',
    'stats': {'3pt': 92, 'ath': 92, 'clu': 99, 'def': 99, 'ins': 94, 'ply': 85},
    'team': 'TOR',
    'theme': 'TheClawLock •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clutch Performer', 'HOF Menace', 'HOF Fearless Finisher', 'HOF Clamps'],
    'id': 'go-butler-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/b/be/Jimmy_Butler_2020.jpg',
    'jersey': 22,
    'name': 'Jimmy Butler',
    'ovr': 97,
    'pos': 'SF',
    'quote': '2xNBAFinalsLeader• • •   5x• A ll- Defensive• • •   TheColdest •   PlayoffEnforcerinthe• E • a st •',
    'sec_pos': 'SG',
    'stats': {'3pt': 85, 'ath': 92, 'clu': 99, 'def': 98, 'ins': 96, 'ply': 90},
    'team': 'MIA',
    'theme': 'PlayoffJimmy •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Stepback Maestro', 'HOF Space Creator', 'HOF Handles For Days', 'HOF Dimer'],
    'id': 'go-jamesharden-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/6/63/Harden_dribbling_midcourt%2C_Cavaliers_vs_Nets_on_January_17%2C_2022_%28cropped%29.jpg/1280px-Harden_dribbling_midcourt%2C_Cavaliers_vs_Nets_on_January_17%2C_2022_%28cropped%29.jpg',
    'jersey': 1,
    'name': 'James Harden',
    'ovr': 97,
    'pos': 'SG',
    'quote': '2018NBAMVP• • •   3xScoring• C hampion• • •   10xAll- Star• • • 6 • 0 • - PtTriple- Double •',
    'sec_pos': 'PG',
    'stats': {'3pt': 95, 'ath': 96, 'clu': 95, 'def': 93, 'ins': 96, 'ply': 93},
    'team': 'HOU',
    'theme': 'TheStepbackMVP •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Quick First Step', 'HOF Dimer', 'HOF Acrobat', 'HOF Handles For Days'],
    'id': 'go-granthill-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/0/05/Grant_Hill_2007-12-08.jpg/1280px-Grant_Hill_2007-12-08.jpg',
    'jersey': 33,
    'name': 'Grant Hill',
    'ovr': 97,
    'pos': 'SF',
    'quote': '7xAll- Star• • •   5xAll- NBA• • •   Triple- DoubleSensation •',
    'sec_pos': 'PG',
    'stats': {'3pt': 96, 'ath': 99, 'clu': 99, 'def': 96, 'ins': 98, 'ply': 93},
    'team': 'DET',
    'theme': 'PointForwardPhenom •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Glove', 'HOF Clamps', 'HOF Menace', 'HOF Interceptor'],
    'id': 'go-garypayton-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/14/Gary_Payton%2C_Miami_Heat_circa_2007_%28cropped%29.jpg',
    'jersey': 20,
    'name': 'Gary Payton',
    'ovr': 97,
    'pos': 'PG',
    'quote': '2006NBAChampion• • •   1996• D • P OY• • •   9xAll- Star• • •   9xAll- DefensiveFirstTeam •',
    'sec_pos': 'SG',
    'stats': {'3pt': 98, 'ath': 96, 'clu': 93, 'def': 93, 'ins': 89, 'ply': 96},
    'team': 'SEA',
    'theme': 'TheGloveDPOYGuard •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Clamps', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-dwighthoward-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/41/Dwight_Howard_pre-game_%28cropped%29.jpg/1280px-Dwight_Howard_pre-game_%28cropped%29.jpg',
    'jersey': 12,
    'name': 'Dwight Howard',
    'ovr': 97,
    'pos': 'SG',
    'quote': 'HallofFameLegend• • •   8x• N • B • A •   All- Star• ( 2007– 2014) • • • E ra- DefiningSuperstar •',
    'sec_pos': 'PF',
    'stats': {'3pt': 99, 'ath': 99, 'clu': 99, 'def': 97, 'ins': 98, 'ply': 92},
    'team': 'BOS',
    'theme': 'HallofFameLegend• ( 8xAll • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Anchor', 'HOF Deadeye', 'HOF Clutch Shooter'],
    'id': 'go-donovanmitchell-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/39/Donovan_Mitchell_Pregame.jpg/1280px-Donovan_Mitchell_Pregame.jpg',
    'jersey': 45,
    'name': 'Donovan Mitchell',
    'ovr': 97,
    'pos': 'C',
    'quote': 'HallofFameLegend• • •   7x• N • B • A •   All- Star• ( 2020– 2026) • • • E ra- DefiningSuperstar •',
    'sec_pos': 'PG',
    'stats': {'3pt': 75, 'ath': 99, 'clu': 94, 'def': 99, 'ins': 98, 'ply': 84},
    'team': 'CLE',
    'theme': 'HallofFameLegend• ( 7xAll • - Star) •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Anchor', 'HOF Rim Protector', 'HOF Post Lock', 'HOF Chase Down Artist'],
    'id': 'go-dikembemutombo-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/e8/Lipofsky-Dikembe_Mutombo_%28cropped%29.jpg',
    'jersey': 55,
    'name': 'Dikembe Mutombo',
    'ovr': 97,
    'pos': 'C',
    'quote': '4xNBADefensivePlayerof •   theYear• • •   8xAll- Star• • • F ingerWagIcon •',
    'sec_pos': 'PF',
    'stats': {'3pt': 50, 'ath': 91, 'clu': 89, 'def': 98, 'ins': 87, 'ply': 61},
    'team': 'DEN',
    'theme': 'FingerWag4xDPOY •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Floor General', 'HOF Dimer', 'HOF Middy Magician', 'HOF Glove'],
    'id': 'go-chrispaul-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ad/Chris_Paul_%282022_All-Star_Weekend%29_%28cropped%29.jpg/1280px-Chris_Paul_%282022_All-Star_Weekend%29_%28cropped%29.jpg',
    'jersey': 3,
    'name': 'Chris Paul',
    'ovr': 97,
    'pos': 'PG',
    'quote': '12xAll- Star• • •   5xNBAAssis tsLeader• • •   6xStealsLead er• • •   PointGod •',
    'sec_pos': 'SG',
    'stats': {'3pt': 93, 'ath': 89, 'clu': 97, 'def': 95, 'ins': 88, 'ply': 98},
    'team': 'SAS',
    'theme': 'PointGodFloorGeneral •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Triple Threat', 'HOF Middy Magician', 'HOF Bully', 'HOF Catch & Shoot'],
    'id': 'go-carmeloanthony-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/27/Carmelo_Anthony_at_2025_NBA_All_Star_Weekend_%28cropped%29.jpg/1280px-Carmelo_Anthony_at_2025_NBA_All_Star_Weekend_%28cropped%29.jpg',
    'jersey': 7,
    'name': 'Carmelo Anthony',
    'ovr': 97,
    'pos': 'SF',
    'quote': '10xAll- Star• • •   2013Scoring •   Champion• • •   Over28, 000Ca reerPoints •',
    'sec_pos': 'PF',
    'stats': {'3pt': 95, 'ath': 99, 'clu': 99, 'def': 97, 'ins': 99, 'ply': 97},
    'team': 'NYK',
    'theme': 'OlympicGold• & •   62- PtMSG •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Special Delivery', 'HOF Needle Threader', 'HOF Floor General', 'HOF Dimer'],
    'id': 'go-bobcousy-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/c5/Bob_Cousy_%281%29.jpeg',
    'jersey': 14,
    'name': 'Bob Cousy',
    'ovr': 97,
    'pos': 'PG',
    'quote': '6xNBAChampion• • •   1957MVP • • •   13xAll- Star• • •   8xNBA• A • s sistsLeader •',
    'sec_pos': 'SG',
    'stats': {'3pt': 95, 'ath': 95, 'clu': 97, 'def': 95, 'ins': 94, 'ply': 99},
    'team': 'BOS',
    'theme': 'HoudinioftheHardwood •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Anchor', 'HOF Rebound Chaser', 'HOF Pogo Stick', 'HOF Post Lock'],
    'id': 'go-ad-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/3/36/Anthony_Davis_2020.jpg',
    'jersey': 3,
    'name': 'Anthony Davis',
    'ovr': 97,
    'pos': 'C',
    'quote': '2020NBAChampion• • •   4xAll- DefensiveFirstTeam• • •   Dom inantRimProtector •',
    'sec_pos': 'PF',
    'stats': {'3pt': 80, 'ath': 94, 'clu': 94, 'def': 99, 'ins': 98, 'ply': 82},
    'team': 'LAL',
    'theme': 'TheBrowAnchor •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Anchor', 'HOF Rim Protector', 'HOF Post Lock', 'HOF Rebound Chaser'],
    'id': 'go-alonzomourning-97',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b7/Alonzo_Mourning.jpg/1280px-Alonzo_Mourning.jpg',
    'jersey': 33,
    'name': 'Alonzo Mourning',
    'ovr': 97,
    'pos': 'C',
    'quote': '2006NBAChampion• • •   2xDPOY • • •   7xAll- Star• • •   Defensive •   Warrior •',
    'sec_pos': 'PF',
    'stats': {'3pt': 73, 'ath': 95, 'clu': 93, 'def': 99, 'ins': 99, 'ply': 90},
    'team': 'MIA',
    'theme': '2xDPOYPaintProtector •',
    'tier': 'galaxy_opal'},
  { 'badges': ['HOF Ankle Breaker', 'HOF Giant Slayer', 'HOF Acrobat', 'HOF Quick First Step'],
    'id': 'go-iverson-97',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/3/33/Alex_Caruso_%2852480104636%29_%28cropped%29.jpg',
    'jersey': 23,
    'name': 'Allen Iverson',
    'ovr': 97,
    'pos': 'PG',
    'quote': '2001NBAMVP• • •   4xScoring• C hampion• • •   CulturalIconwi ththeMostLethalCrossove • r •',
    'sec_pos': 'SG',
    'stats': {'3pt': 90, 'ath': 99, 'clu': 98, 'def': 92, 'ins': 97, 'ply': 96},
    'team': 'PHI',
    'theme': 'TheAnswer •',
    'tier': 'galaxy_opal'},
  { 'badges': ['Gold Clamps', 'Gold Middy Magician', 'Gold Fearless Finisher', 'Gold Dimer'],
    'id': 'dia-sga-95',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/d/dc/Shai_Gilgeous-Alexander_2024.jpg',
    'jersey': 2,
    'name': 'Shai Gilgeous-Alexander',
    'ovr': 96,
    'pos': 'PG',
    'quote': '2xAll- NBAFirstTeam• • •   Clu tchPlayeroftheYearFin alist• • •   KingoftheMid- Ran geDrive •',
    'sec_pos': 'SG',
    'stats': {'3pt': 90, 'ath': 93, 'clu': 97, 'def': 94, 'ins': 96, 'ply': 95},
    'team': 'OKC',
    'theme': 'SmoothMVPFinalist •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-klaythompson-96',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/8/81/Klay_Thompson_%28cropped%29.jpg/1280px-Klay_Thompson_%28cropped%29.jpg',
    'jersey': 11,
    'name': 'Klay Thompson',
    'ovr': 96,
    'pos': 'SG',
    'quote': '5xNBAAll- Star• ( 2015– 2019) • • •   DominantFranchiseCorn erstone •',
    'sec_pos': 'PG',
    'stats': {'3pt': 96, 'ath': 88, 'clu': 95, 'def': 93, 'ins': 84, 'ply': 82},
    'team': 'DAL',
    'theme': 'FranchiseAll- Star• ( 5x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-karlanthonytowns-96',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/55/Karl-Anthony_Towns_%2851914283512%29_%28cropped%29_%28cropped%29.jpg/1280px-Karl-Anthony_Towns_%2851914283512%29_%28cropped%29_%28cropped%29.jpg',
    'jersey': 32,
    'name': 'Karl-Anthony Towns',
    'ovr': 96,
    'pos': 'PG',
    'quote': '6xNBAAll- Star• ( 2018– 2019; •   2022; •   2024– 2026) • • •   Domina ntFranchiseCornerstone •',
    'sec_pos': 'C',
    'stats': {'3pt': 97, 'ath': 95, 'clu': 97, 'def': 90, 'ins': 92, 'ply': 99},
    'team': 'NYK',
    'theme': 'FranchiseAll- Star• ( 6x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-jaylenbrown-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/8/84/Celtics_at_Wizards_2024-12-015_%28cropped%29_%28cropped%29.jpg',
    'jersey': 7,
    'name': 'Jaylen Brown',
    'ovr': 96,
    'pos': 'SG',
    'quote': '5xNBAAll- Star• ( 2021; •   2023 • – 2026) • • •   DominantFranchis • e •   Cornerstone •',
    'sec_pos': 'C',
    'stats': {'3pt': 98, 'ath': 96, 'clu': 95, 'def': 94, 'ins': 94, 'ply': 93},
    'team': 'BOS',
    'theme': 'FranchiseAll- Star• ( 5x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Post Spin Technician', 'Gold Anchor', 'Gold Dream Shake', 'Gold Post Lock'],
    'id': 'dia-hakeem-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/3/38/Hakeem_Olajuwon_2015.jpg',
    'jersey': 34,
    'name': 'Hakeem Olajuwon',
    'ovr': 96,
    'pos': 'C',
    'quote': '2xNBAChampion• • •   2xFinals •   MVP• • •   1994MVP• • •   All- Time •   NBABlocksLeader •',
    'sec_pos': 'PF',
    'stats': {'3pt': 62, 'ath': 92, 'clu': 96, 'def': 99, 'ins': 98, 'ply': 82},
    'team': 'HOU',
    'theme': 'TheDreamShake •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-devinbooker-96',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/2/22/Devin_Booker%2C_Olympic_Games_2024_%28cropped%29.jpg',
    'jersey': 1,
    'name': 'Devin Booker',
    'ovr': 96,
    'pos': 'C',
    'quote': '5xNBAAll- Star• ( 2020– 2022; •   2024; •   2026) • • •   DominantFr anchiseCornerstone •',
    'sec_pos': 'PF',
    'stats': {'3pt': 75, 'ath': 95, 'clu': 92, 'def': 99, 'ins': 99, 'ply': 89},
    'team': 'PHX',
    'theme': 'FranchiseAll- Star• ( 5x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-blakegriffin-96',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/7e/Blake_Griffin_with_ball_20131118_Clippers_v_Grizzles.jpg/1280px-Blake_Griffin_with_ball_20131118_Clippers_v_Grizzles.jpg',
    'jersey': 32,
    'name': 'Blake Griffin',
    'ovr': 96,
    'pos': 'C',
    'quote': '6xNBAAll- Star• ( 2011– 2015; •   2019) • • •   DominantFranchis • e •   Cornerstone •',
    'sec_pos': 'PG',
    'stats': {'3pt': 73, 'ath': 94, 'clu': 97, 'def': 99, 'ins': 99, 'ply': 85},
    'team': 'CLE',
    'theme': 'FranchiseAll- Star• ( 6x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-traeyoung-95',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/42/Trae_Young_%282022_All-Star_Weekend%29_%28cropped%29.jpg/1280px-Trae_Young_%282022_All-Star_Weekend%29_%28cropped%29.jpg',
    'jersey': 11,
    'name': 'Trae Young',
    'ovr': 95,
    'pos': 'SF',
    'quote': '4xNBAAll- Star• ( 2020; •   2022 • ; •   2024– 2025) • • •   DominantFr anchiseCornerstone •',
    'sec_pos': 'PG',
    'stats': {'3pt': 96, 'ath': 96, 'clu': 95, 'def': 96, 'ins': 99, 'ply': 95},
    'team': 'ATL',
    'theme': 'FranchiseAll- Star• ( 4x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-pennyhardaway-95',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/2/25/HBCUAllstarBasketball4223-118_%2852802377149%29_%28cropped%29.jpg',
    'jersey': 1,
    'name': 'Penny Hardaway',
    'ovr': 95,
    'pos': 'C',
    'quote': '4xNBAAll- Star• ( 1995– 1998) • • •   DominantFranchiseCorn erstone •',
    'sec_pos': 'SF',
    'stats': {'3pt': 72, 'ath': 92, 'clu': 96, 'def': 97, 'ins': 99, 'ply': 83},
    'team': 'SAS',
    'theme': 'FranchiseAll- Star• ( 4x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Ankle Breaker', 'Gold Handles For Days', 'Gold Circus Threes', 'Gold Layup Package'],
    'id': 'dia-kyrie-95',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/42/Kyrie_Irving_2021.jpg',
    'jersey': 11,
    'name': 'Kyrie Irving',
    'ovr': 95,
    'pos': 'PG',
    'quote': '2016NBAChampion• • •   8xAll- Star• • •   GreatestBall- Handl ingPackageinHistory •',
    'sec_pos': 'SG',
    'stats': {'3pt': 96, 'ath': 91, 'clu': 98, 'def': 80, 'ins': 97, 'ply': 94},
    'team': 'DAL',
    'theme': 'AnkleBreakerMaster •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-draymondgreen-95',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/9/99/Draymond_Green_2022.jpg/1280px-Draymond_Green_2022.jpg',
    'jersey': 23,
    'name': 'Draymond Green',
    'ovr': 95,
    'pos': 'PF',
    'quote': '4xNBAAll- Star• ( 2016– 2018; •   2022) • • •   DominantFranchis • e •   Cornerstone •',
    'sec_pos': 'C',
    'stats': {'3pt': 93, 'ath': 99, 'clu': 99, 'def': 90, 'ins': 93, 'ply': 90},
    'team': 'GSW',
    'theme': 'FranchiseAll- Star• ( 4x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Deadeye', 'Gold Catch & Shoot', 'Gold Middy Magician', 'Gold Clutch Shooter'],
    'id': 'dia-dirk-95',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/9/91/Dirk_Nowitzki_2018.jpg',
    'jersey': 41,
    'name': 'Dirk Nowitzki',
    'ovr': 95,
    'pos': 'PF',
    'quote': '2011NBAChampion• & •   Finals •   MVP• • •   2007MVP• • •   Over31, • 0 00CareerPoints •',
    'sec_pos': 'C',
    'stats': {'3pt': 96, 'ath': 82, 'clu': 98, 'def': 82, 'ins': 94, 'ply': 80},
    'team': 'DAL',
    'theme': 'One- LegFadeaway •',
    'tier': 'diamond'},
  { 'badges': ['Gold Posterizer', 'Gold Limitless Takeoff', 'Gold Clamps', 'Gold Agent 3'],
    'id': 'dia-ant-95',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/10/Anthony_Edwards_2024.jpg',
    'jersey': 5,
    'name': 'Anthony Edwards',
    'ovr': 95,
    'pos': 'SG',
    'quote': '2xAll- Star• • •   WesternConfe renceFinalsLeader• • •   Elec trifyingAerialDunker •',
    'sec_pos': 'SF',
    'stats': {'3pt': 92, 'ath': 98, 'clu': 96, 'def': 94, 'ins': 97, 'ply': 88},
    'team': 'MIN',
    'theme': 'Ant- ManPosterizer •',
    'tier': 'diamond'},
  { 'badges': ['Gold Needle Threader', 'Gold Dimer', 'Gold Limitless Range', 'Gold Floor General'],
    'id': 'dia-hali-94',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/a/a2/Tyrese_Haliburton_2024.jpg',
    'jersey': 0,
    'name': 'Tyrese Haliburton',
    'ovr': 94,
    'pos': 'PG',
    'quote': '2xAll- Star• • •   NBAAssists• L eader• • •   In- SeasonTourname ntSuperstar •',
    'sec_pos': 'SG',
    'stats': {'3pt': 94, 'ath': 89, 'clu': 95, 'def': 80, 'ins': 88, 'ply': 99},
    'team': 'IND',
    'theme': 'DimerSpecialist •',
    'tier': 'diamond'},
  { 'badges': ['Silver Deadeye', 'Silver Hot Zone Hunter', 'Silver Posterizer'],
    'id': 'dia-tatum-94',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/c8/Jayson_Tatum_Parade_2024.jpg',
    'jersey': 0,
    'name': 'Jayson Tatum',
    'ovr': 94,
    'pos': 'SF',
    'quote': '2024NBAChampion• & •   Finals •   MVP• - •   5xAll- StarBoston• L egend •',
    'sec_pos': 'PF',
    'stats': {'3pt': 88, 'ath': 90, 'clu': 94, 'def': 88, 'ins': 92, 'ply': 90},
    'team': 'BOS',
    'theme': '2024Champion •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-jalenbrunson-94',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/f/f2/Jalen_Brunson_2023_%28cropped%29.jpg',
    'jersey': 11,
    'name': 'Jalen Brunson',
    'ovr': 94,
    'pos': 'SF',
    'quote': '3xNBAAll- Star• ( 2024– 2026) • • •   DominantFranchiseCorn erstone •',
    'sec_pos': 'PF',
    'stats': {'3pt': 95, 'ath': 98, 'clu': 97, 'def': 95, 'ins': 94, 'ply': 90},
    'team': 'NYK',
    'theme': 'FranchiseAll- Star• ( 3x) •',
    'tier': 'diamond'},
  { 'badges': ['Silver Giant Slayer', 'Silver Posterizer', 'Silver Anchor', 'Silver Brick Wall'],
    'id': 'dia-giannis-94',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/4d/Giannis_Antetokounmpo_2021.jpg',
    'jersey': 34,
    'name': 'Giannis Antetokounmpo',
    'ovr': 94,
    'pos': 'PF',
    'quote': '2021NBAChampion• & •   Finals •   MVP• - •   2xMVP• - •   GreekFreak •   DominantForce •',
    'sec_pos': 'C',
    'stats': {'3pt': 55, 'ath': 99, 'clu': 91, 'def': 95, 'ins': 98, 'ply': 88},
    'team': 'MIL',
    'theme': '2xMVPGreekFreak •',
    'tier': 'diamond'},
  { 'badges': ['Gold Limitless Range', 'Gold Posterizer', 'Gold Acrobat', 'Gold Space Creator'],
    'id': 'dia-spida-94',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/9/94/Donovan_Mitchell_2022.jpg',
    'jersey': 45,
    'name': 'Donovan Mitchell',
    'ovr': 94,
    'pos': 'SG',
    'quote': '5xAll- Star• • •   DunkContest •   Champion• • •   71- PointScorin • g •   Masterpiece •',
    'sec_pos': 'PG',
    'stats': {'3pt': 94, 'ath': 96, 'clu': 95, 'def': 84, 'ins': 95, 'ply': 90},
    'team': 'CLE',
    'theme': '71- PtExplosion •',
    'tier': 'diamond'},
  { 'badges': ['Gold Deadeye', 'Gold Catch & Shoot', 'Gold Green Machine', 'Gold Ankle Breaker'],
    'id': 'dia-booker-94',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/a/ad/Devin_Booker_2022.jpg',
    'jersey': 1,
    'name': 'Devin Booker',
    'ovr': 94,
    'pos': 'SG',
    'quote': '4xAll- Star• • •   OlympicGold •   Medalist• • •   Scored70Point • s •   inSingleGame •',
    'sec_pos': 'PG',
    'stats': {'3pt': 95, 'ath': 89, 'clu': 96, 'def': 82, 'ins': 92, 'ply': 91},
    'team': 'PHX',
    'theme': '70- PtScorer •',
    'tier': 'diamond'},
  { 'badges': ['Gold Limitless Range', 'Gold Clutch Shooter', 'Gold Agent 3', 'Gold Deadeye'],
    'id': 'dia-dame-94',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/9/91/Damian_Lillard_2021.jpg',
    'jersey': 0,
    'name': 'Damian Lillard',
    'ovr': 94,
    'pos': 'PG',
    'quote': '8xAll- Star• • •   NBA75thAnni versaryTeam• • •   2x3PTCont estChampion •',
    'sec_pos': 'SG',
    'stats': {'3pt': 97, 'ath': 91, 'clu': 99, 'def': 78, 'ins': 90, 'ply': 92},
    'team': 'MIL',
    'theme': 'DameTimeClutch •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-bamadebayo-94',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/7/7d/Bam_Adebayo_%28cropped%29.jpg',
    'jersey': 13,
    'name': 'Bam Adebayo',
    'ovr': 94,
    'pos': 'C',
    'quote': '3xNBAAll- Star• ( 2020; •   2023 • – 2024) • • •   DominantFranchis • e •   Cornerstone •',
    'sec_pos': 'PG',
    'stats': {'3pt': 71, 'ath': 91, 'clu': 91, 'def': 96, 'ins': 99, 'ply': 83},
    'team': 'MIA',
    'theme': 'FranchiseAll- Star• ( 3x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-zionwilliamson-93',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/53/Zion_Williamson_2020_%28cropped%29.jpg/1280px-Zion_Williamson_2020_%28cropped%29.jpg',
    'jersey': 1,
    'name': 'Zion Williamson',
    'ovr': 93,
    'pos': 'SG',
    'quote': '2xNBAAll- Star• ( 2021; •   2023 • ) • • •   DominantFranchiseCor nerstone •',
    'sec_pos': 'C',
    'stats': {'3pt': 92, 'ath': 94, 'clu': 94, 'def': 87, 'ins': 90, 'ply': 92},
    'team': 'NOP',
    'theme': 'FranchiseAll- Star• ( 2x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-victorwembanyama-93',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/6/65/Victor_Wembanyama_San_Antonio_Spurs_2024.jpg/1280px-Victor_Wembanyama_San_Antonio_Spurs_2024.jpg',
    'jersey': 1,
    'name': 'Victor Wembanyama',
    'ovr': 93,
    'pos': 'C',
    'quote': '2xNBAAll- Star• ( 2025– 2026) • • •   DominantFranchiseCorn erstone •',
    'sec_pos': 'SF',
    'stats': {'3pt': 69, 'ath': 96, 'clu': 94, 'def': 98, 'ins': 97, 'ply': 80},
    'team': 'SAS',
    'theme': 'FranchiseAll- Star• ( 2x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-tyresehaliburton-93',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/16/1_tyrese_haliburton_2025_%28cropped_2%29.jpg/1280px-1_tyrese_haliburton_2025_%28cropped_2%29.jpg',
    'jersey': 0,
    'name': 'Tyrese Haliburton',
    'ovr': 93,
    'pos': 'SG',
    'quote': '2xNBAAll- Star• ( 2023– 2024) • • •   DominantFranchiseCorn erstone •',
    'sec_pos': 'SF',
    'stats': {'3pt': 97, 'ath': 96, 'clu': 94, 'def': 93, 'ins': 91, 'ply': 93},
    'team': 'IND',
    'theme': 'FranchiseAll- Star• ( 2x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-jrueholiday-93',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/b/ba/Celtics_at_Wizards_2024-12-021_%28cropped%29.jpg',
    'jersey': 4,
    'name': 'Jrue Holiday',
    'ovr': 93,
    'pos': 'SG',
    'quote': '2xNBAAll- Star• ( 2013; •   2023 • ) • • •   DominantFranchiseCor nerstone •',
    'sec_pos': 'C',
    'stats': {'3pt': 92, 'ath': 96, 'clu': 95, 'def': 88, 'ins': 94, 'ply': 93},
    'team': 'BOS',
    'theme': 'FranchiseAll- Star• ( 2x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Posterizer', 'Gold Limitless Takeoff', 'Gold Quick First Step', 'Gold Dimer'],
    'id': 'dia-morant-93',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/14/Ja_Morant_2022.jpg',
    'jersey': 12,
    'name': 'Ja Morant',
    'ovr': 93,
    'pos': 'PG',
    'quote': '2xAll- Star• • •   MostImproved •   Player• • •   UnrivaledVertic alLeap• & •   FastbreakFlash •',
    'sec_pos': 'SG',
    'stats': {'3pt': 85, 'ath': 99, 'clu': 94, 'def': 82, 'ins': 98, 'ply': 95},
    'team': 'MEM',
    'theme': 'GravityDefier •',
    'tier': 'diamond'},
  { 'badges': ['Gold Clamps', 'Gold Deadeye', 'Gold Quick First Step'],
    'id': 'dia-deaaronfox-93',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/f/fa/De%27Aaron_Fox_%28cropped%29.jpg',
    'jersey': 5,
    'name': "De'Aaron Fox",
    'ovr': 93,
    'pos': 'PG',
    'quote': '2xNBAAll- Star• ( 2023; •   2026 • ) • • •   DominantFranchiseCor nerstone •',
    'sec_pos': 'SF',
    'stats': {'3pt': 91, 'ath': 94, 'clu': 88, 'def': 87, 'ins': 87, 'ply': 97},
    'team': 'SAC',
    'theme': 'FranchiseAll- Star• ( 2x) •',
    'tier': 'diamond'},
  { 'badges': ['Gold Anchor', 'Gold Clamps', 'Gold Interceptor', 'Gold Rebound Chaser'],
    'id': 'dia-bam-93',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/ee/Bam_Adebayo_2022.jpg',
    'jersey': 13,
    'name': 'Bam Adebayo',
    'ovr': 93,
    'pos': 'C',
    'quote': '3xAll- Star• • •   5xAll- Defens iveTeam• • •   Versatile• 1 • - thr ough- • 5 •   DefensiveAnchor •',
    'sec_pos': 'PF',
    'stats': {'3pt': 72, 'ath': 93, 'clu': 91, 'def': 98, 'ins': 93, 'ply': 88},
    'team': 'MIA',
    'theme': 'DPOYFinalist •',
    'tier': 'diamond'},
  { 'badges': ['Silver Anchor', 'Silver Brick Wall', 'Silver Posterizer', 'Silver Intimidator'],
    'id': 'dia-adavis-93',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/3/36/Anthony_Davis_2020.jpg',
    'jersey': 3,
    'name': 'Anthony Davis',
    'ovr': 93,
    'pos': 'PF',
    'quote': '2020NBAChampion• - •   8xAll- Star• - •   EliteTwo- WaySuper star •',
    'sec_pos': 'C',
    'stats': {'3pt': 62, 'ath': 96, 'clu': 90, 'def': 97, 'ins': 97, 'ply': 82},
    'team': 'LAL',
    'theme': 'BrowDominance •',
    'tier': 'diamond'},
  { 'badges': ['Gold Middy Magician', 'Gold Fearless Finisher', 'Gold Dimer'],
    'id': 'amy-brunson-92',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/f/f2/Jalen_Brunson_2023_%28cropped%29.jpg',
    'jersey': 11,
    'name': 'Jalen Brunson',
    'ovr': 92,
    'pos': 'PG',
    'quote': 'All- NBASecondTeam• • •   MSG• P layoffHero• • •   Masterofth • e •   Pivot• & •   Footwork •',
    'sec_pos': 'SG',
    'stats': {'3pt': 92, 'ath': 88, 'clu': 97, 'def': 82, 'ins': 94, 'ply': 93},
    'team': 'NYK',
    'theme': 'GardenMVP •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Catch & Shoot', 'Gold Fearless Finisher', 'Gold Dimer'],
    'id': 'amy-manuginobili-91',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/33/Manu_Ginobili_Spurs-Magic011_%28cropped%29.jpg/1280px-Manu_Ginobili_Spurs-Magic011_%28cropped%29.jpg',
    'jersey': 25,
    'name': 'Manu Ginobili',
    'ovr': 91,
    'pos': 'SF',
    'quote': '2xNBAAll- Star• ( 2005; •   2011 • ) • • •   HighImpactScoringDy namo •',
    'sec_pos': 'PG',
    'stats': {'3pt': 86, 'ath': 95, 'clu': 94, 'def': 93, 'ins': 95, 'ply': 91},
    'team': 'CHI',
    'theme': 'All- StarPerformer• ( 2x) •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Posterizer', 'Gold Clamps', 'Gold Menace'],
    'id': 'amy-brown-91',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/c/c2/Jaylen_Brown_2024.jpg',
    'jersey': 7,
    'name': 'Jaylen Brown',
    'ovr': 91,
    'pos': 'SG',
    'quote': '2024NBAFinalsMVP• • •   3x• A • l • l • - Star• • •   Two- WayExplosive •   Wing •',
    'sec_pos': 'SF',
    'stats': {'3pt': 88, 'ath': 96, 'clu': 93, 'def': 94, 'ins': 94, 'ply': 82},
    'team': 'BOS',
    'theme': 'FinalsMVP •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Catch & Shoot', 'Gold Fearless Finisher', 'Gold Dimer'],
    'id': 'amy-billwalton-91',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/5/54/Bill_walton_blazers_photo.jpg',
    'jersey': 42,
    'name': 'Bill Walton',
    'ovr': 91,
    'pos': 'PF',
    'quote': '2xNBAAll- Star• ( 1977– 1978) • • •   HighImpactScoringDyn amo •',
    'sec_pos': 'SF',
    'stats': {'3pt': 76, 'ath': 89, 'clu': 88, 'def': 90, 'ins': 92, 'ply': 81},
    'team': 'OKC',
    'theme': 'All- StarPerformer• ( 2x) •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Bully', 'Gold Posterizer', 'Gold Fast Twitch'],
    'id': 'amy-zion-90',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/8/8d/Zion_Williamson_2022.jpg',
    'jersey': 1,
    'name': 'Zion Williamson',
    'ovr': 90,
    'pos': 'PF',
    'quote': '2xAll- Star• • •   Unstoppable• A bove- the- RimPowerForward •',
    'sec_pos': 'C',
    'stats': {'3pt': 62, 'ath': 98, 'clu': 91, 'def': 84, 'ins': 98, 'ply': 85},
    'team': 'NOP',
    'theme': 'PaintBulldozer •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Bully', 'Gold Space Creator', 'Gold Dimer'],
    'id': 'amy-paolo-90',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/1e/Paolo_Banchero_2024.jpg',
    'jersey': 5,
    'name': 'Paolo Banchero',
    'ovr': 90,
    'pos': 'PF',
    'quote': '2024All- Star• • •   2023Rookie •   oftheYear• • •   Dominant6f • t •   10inPlaymaker •',
    'sec_pos': 'SF',
    'stats': {'3pt': 84, 'ath': 91, 'clu': 92, 'def': 87, 'ins': 93, 'ply': 89},
    'team': 'ORL',
    'theme': 'All- StarPointForward •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Catch & Shoot', 'Gold Deadeye', 'Gold Rebound Chaser'],
    'id': 'amy-kat-90',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/a/ae/Karl-Anthony_Towns_2023.jpg',
    'jersey': 32,
    'name': 'Karl-Anthony Towns',
    'ovr': 90,
    'pos': 'C',
    'quote': '4xAll- Star• • • 3 • - PointConte stChampion• • •   PureElite• S hootingCenter •',
    'sec_pos': 'PF',
    'stats': {'3pt': 95, 'ath': 86, 'clu': 90, 'def': 84, 'ins': 94, 'ply': 80},
    'team': 'NYK',
    'theme': '3PTContestChampBig •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Quick First Step', 'Gold Clutch Shooter', 'Gold Interceptor'],
    'id': 'amy-fox-90',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/e9/De%27Aaron_Fox_2023.jpg',
    'jersey': 5,
    'name': "De'Aaron Fox",
    'ovr': 90,
    'pos': 'PG',
    'quote': 'InauguralNBAClutchPlayer •   oftheYear• • •   FastestSpe edWithBallintheLeague •',
    'sec_pos': 'SG',
    'stats': {'3pt': 88, 'ath': 99, 'clu': 98, 'def': 88, 'ins': 92, 'ply': 90},
    'team': 'SAC',
    'theme': 'InauguralClutchPOTY •',
    'tier': 'amethyst'},
  { 'badges': ['Bronze Posterizer', 'Bronze Catch & Shoot', 'Bronze Clamps'],
    'id': 'amy-aedwards-90',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/10/Anthony_Edwards_2024.jpg',
    'jersey': 5,
    'name': 'Anthony Edwards',
    'ovr': 90,
    'pos': 'SG',
    'quote': "2xAll- Star• - •   TeamUSAGold •   Medalist• - •   Minnesota' • s •   Fr anchiseStar •",
    'sec_pos': 'SF',
    'stats': {'3pt': 86, 'ath': 97, 'clu': 90, 'def': 86, 'ins': 90, 'ply': 84},
    'team': 'MIN',
    'theme': 'Ant- ManRising •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Limitless Range', 'Gold Dimer', 'Gold Handles For Days'],
    'id': 'amy-trae-89',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/6/65/Trae_Young_2022.jpg',
    'jersey': 11,
    'name': 'Trae Young',
    'ovr': 89,
    'pos': 'PG',
    'quote': '3xAll- Star• • •   LedNBAin• T • o talPoints• & •   Assists• • •   Log • o •   3PTSniper •',
    'sec_pos': 'SG',
    'stats': {'3pt': 95, 'ath': 88, 'clu': 96, 'def': 70, 'ins': 84, 'ply': 98},
    'team': 'ATL',
    'theme': 'IceTraeDeep• 3 •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Special Delivery', 'Gold Needle Threader', 'Gold Limitless Range'],
    'id': 'amy-lamelo-89',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/b/b9/LaMelo_Ball_2022.jpg',
    'jersey': 1,
    'name': 'LaMelo Ball',
    'ovr': 89,
    'pos': 'PG',
    'quote': '2022All- Star• • •   2021Rookie •   oftheYear• • •   Highlight• R eelPassingVision •',
    'sec_pos': 'SG',
    'stats': {'3pt': 90, 'ath': 90, 'clu': 91, 'def': 78, 'ins': 86, 'ply': 97},
    'team': 'CHA',
    'theme': 'FlashyPasser •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Clutch Shooter', 'Gold Difficult Shots', 'Gold Acrobat'],
    'id': 'amy-murray-89',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/0/07/Jamal_Murray_2023.jpg',
    'jersey': 27,
    'name': 'Jamal Murray',
    'ovr': 89,
    'pos': 'PG',
    'quote': '2023NBAChampion• • •   Multipl • e •   PlayoffGame- WinningBuz zerBeaters •',
    'sec_pos': 'SG',
    'stats': {'3pt': 92, 'ath': 89, 'clu': 99, 'def': 81, 'ins': 90, 'ply': 90},
    'team': 'DEN',
    'theme': 'PlayoffBucket •',
    'tier': 'amethyst'},
  { 'badges': ['Gold Anchor', 'Gold Chase Down Artist', 'Gold Catch & Shoot'],
    'id': 'amy-chet-89',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/b/b8/Chet_Holmgren_2024.jpg',
    'jersey': 7,
    'name': 'Chet Holmgren',
    'ovr': 89,
    'pos': 'C',
    'quote': 'All- RookieFirstTeam• • •   7ft •   1inShot- Blocking• & •   3PT• S hootingPhenom •',
    'sec_pos': 'PF',
    'stats': {'3pt': 89, 'ath': 88, 'clu': 90, 'def': 96, 'ins': 89, 'ply': 80},
    'team': 'OKC',
    'theme': 'Shot- BlockingPhenom •',
    'tier': 'amethyst'},
  { 'badges': ['Bronze Anchor', 'Bronze Intimidator', 'Bronze Aerial Wizard'],
    'id': 'ruby-wemby-88',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/ec/Victor_Wembanyama_2024.jpg',
    'jersey': 1,
    'name': 'Victor Wembanyama',
    'ovr': 88,
    'pos': 'C',
    'quote': '2024RookieoftheYear• - • G enerationalTalent• - •   Extra terrestrialBlocker •',
    'sec_pos': 'PF',
    'stats': {'3pt': 82, 'ath': 92, 'clu': 84, 'def': 97, 'ins': 90, 'ply': 84},
    'team': 'SAS',
    'theme': 'AlienProdigy •',
    'tier': 'ruby'},
  { 'badges': ['Bronze Lob City Passer', 'Bronze Agent 3', 'Bronze Dimer'],
    'id': 'ruby-trae-87',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/6/65/Trae_Young_2022.jpg',
    'jersey': 11,
    'name': 'Trae Young',
    'ovr': 87,
    'pos': 'PG',
    'quote': '5xAll- Star• - •   EliteLobPas ser• & •   DeepThree- PointThr eat •',
    'sec_pos': 'SG',
    'stats': {'3pt': 90, 'ath': 75, 'clu': 91, 'def': 60, 'ins': 72, 'ply': 95},
    'team': 'ATL',
    'theme': 'IceTraeMaestro •',
    'tier': 'ruby'},
  { 'badges': ['Bronze Giant Slayer', 'Bronze Posterizer', 'Bronze Brick Wall'],
    'id': 'ruby-zion-86',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/8/8d/Zion_Williamson_2022.jpg',
    'jersey': 1,
    'name': 'Zion Williamson',
    'ovr': 86,
    'pos': 'PF',
    'quote': '2021All- Star• - •   MostPowerf ulYoungForceintheNBAPaint •',
    'sec_pos': 'C',
    'stats': {'3pt': 60, 'ath': 99, 'clu': 84, 'def': 83, 'ins': 96, 'ply': 80},
    'team': 'NOP',
    'theme': 'ZionFreightTrain •',
    'tier': 'ruby'},
  { 'badges': ['Silver Clamps', 'Silver Glove', 'Silver Floor General'],
    'id': 'ruby-jrue-86',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/7/75/Jrue_Holiday_2024.jpg',
    'jersey': 4,
    'name': 'Jrue Holiday',
    'ovr': 86,
    'pos': 'PG',
    'quote': '2xNBAChampion• • •   6xAll- • D • e fensiveTeam• • •   MostRespec tedGuardDefender •',
    'sec_pos': 'SG',
    'stats': {'3pt': 87, 'ath': 88, 'clu': 92, 'def': 97, 'ins': 84, 'ply': 88},
    'team': 'BOS',
    'theme': '2xChampionClamp •',
    'tier': 'ruby'},
  { 'badges': ['Silver Clamps', 'Silver Interceptor', 'Silver Catch & Shoot'],
    'id': 'ruby-white-86',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/18/Derrick_White_2024.jpg',
    'jersey': 9,
    'name': 'Derrick White',
    'ovr': 86,
    'pos': 'SG',
    'quote': '2024NBAChampion• • •   2xAll- DefensiveSecondTeam• • •   Ch ampionshipGlueGuard •',
    'sec_pos': 'PG',
    'stats': {'3pt': 89, 'ath': 87, 'clu': 91, 'def': 94, 'ins': 82, 'ply': 85},
    'team': 'BOS',
    'theme': 'Two- WayGlue •',
    'tier': 'ruby'},
  { 'badges': ['Silver Menace', 'Silver Glove', 'Silver Corner Specialist'],
    'id': 'ruby-anunoby-85',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/3/30/OG_Anunoby_2024.jpg',
    'jersey': 8,
    'name': 'OG Anunoby',
    'ovr': 85,
    'pos': 'SF',
    'quote': '2019NBAChampion• • •   NBASte alsLeader• • •   LockDownPer imeterClamp •',
    'sec_pos': 'PF',
    'stats': {'3pt': 87, 'ath': 90, 'clu': 87, 'def': 95, 'ins': 86, 'ply': 78},
    'team': 'NYK',
    'theme': 'DefensiveMenace •',
    'tier': 'ruby'},
  { 'badges': ['Silver Clamps', 'Silver Pick Dodger', 'Silver Corner Specialist'],
    'id': 'ruby-mikal-85',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/3/3a/Mikal_Bridges_2023.jpg',
    'jersey': 25,
    'name': 'Mikal Bridges',
    'ovr': 85,
    'pos': 'SF',
    'quote': 'NBAIronMan• • •   All- Defensiv • e •   FirstTeam• • • 3 • - and- • D •   Per fection •',
    'sec_pos': 'SG',
    'stats': {'3pt': 88, 'ath': 89, 'clu': 88, 'def': 93, 'ins': 84, 'ply': 81},
    'team': 'NYK',
    'theme': 'IronManLock •',
    'tier': 'ruby'},
  { 'badges': ['Silver Posterizer', 'Silver Aerial Wizard', 'Silver Post Lock'],
    'id': 'ruby-gordon-85',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/8/89/Aaron_Gordon_2023.jpg',
    'jersey': 50,
    'name': 'Aaron Gordon',
    'ovr': 85,
    'pos': 'PF',
    'quote': '2023NBAChampion• • •   Legenda ryDunkContestIcon• • •   Pow erDunker• & •   DefensiveAncho • r •',
    'sec_pos': 'SF',
    'stats': {'3pt': 76, 'ath': 97, 'clu': 88, 'def': 92, 'ins': 95, 'ply': 82},
    'team': 'DEN',
    'theme': 'DunkContestKing •',
    'tier': 'ruby'},
  { 'badges': ['Gold Anchor', 'Gold Post Lockdown', 'Silver Dimer', 'Silver Floor General'],
    'id': 'ruby-green-84',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/1b/Draymond_Green_2022.jpg',
    'name': 'Draymond Green',
    'ovr': 84,
    'pos': 'PF',
    'quote': '4x NBA Champion • 2017 Defensive Player of the Year • Heart & Soul of Dubs',
    'sec_pos': 'C',
    'stats': {'3pt': 72, 'ath': 80, 'clu': 87, 'def': 94, 'ins': 78, 'ply': 88},
    'team': 'GSW',
    'theme': 'Defensive Anchor',
    'tier': 'ruby'},
  { 'badges': ['Silver Dimer', 'Silver Space Creator', 'Silver Middy Magician'],
    'id': 'ruby-reaves-84',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/5/52/Austin_Reaves_2023.jpg',
    'jersey': 15,
    'name': 'Austin Reaves',
    'ovr': 84,
    'pos': 'SG',
    'quote': 'FanFavoritePlaymaker• • • H • i ghIQPick- and- RollBall• H andler •',
    'sec_pos': 'PG',
    'stats': {'3pt': 88, 'ath': 83, 'clu': 91, 'def': 79, 'ins': 85, 'ply': 87},
    'team': 'LAL',
    'theme': 'CraftyPlaymaker •',
    'tier': 'ruby'},
  { 'badges': ['Silver Clamps', 'Silver Catch & Shoot', 'Silver Acrobat'],
    'id': 'ruby-andreiguodala-84',
    'image_url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/58/Heat_Andre_Iguodala_%28cropped%29.jpg/1280px-Heat_Andre_Iguodala_%28cropped%29.jpg',
    'jersey': 95,
    'name': 'Andre Iguodala',
    'ovr': 84,
    'pos': 'C',
    'quote': 'NBAAll- Star• ( 2012) • • •   Tough •   Two- WayCompetitor •',
    'sec_pos': 'SG',
    'stats': {'3pt': 65, 'ath': 87, 'clu': 83, 'def': 91, 'ins': 89, 'ply': 71},
    'team': 'WAS',
    'theme': 'All- StarStandout• ( 2012) •',
    'tier': 'ruby'},
  { 'badges': ['Gold Acrobat', 'Gold Space Creator', 'Silver Dimer'],
    'id': 'gold-ginobili-83',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/7/7e/Manu_Ginobili_2013.jpg',
    'name': 'Manu Ginobili',
    'ovr': 83,
    'pos': 'SG',
    'quote': '4x NBA Champion • Hall of Famer • Legendary 6th Man & Clutch Playmaker',
    'sec_pos': 'SF',
    'stats': {'3pt': 82, 'ath': 80, 'clu': 88, 'def': 79, 'ins': 81, 'ply': 84},
    'team': 'SAS',
    'theme': 'Eurostep Maestro',
    'tier': 'gold'},
  { 'badges': ['Gold Catch & Shoot', 'Gold Corner Specialist', 'Silver Claymore'],
    'id': 'gold-klay-83',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/5/52/Klay_Thompson_2022.jpg',
    'name': 'Klay Thompson',
    'ovr': 83,
    'pos': 'SG',
    'quote': '4x NBA Champion • 5x All-Star • Historic 37-Point Quarter',
    'sec_pos': 'SF',
    'stats': {'3pt': 89, 'ath': 76, 'clu': 86, 'def': 78, 'ins': 75, 'ply': 74},
    'team': 'DAL',
    'theme': 'Splash Brother',
    'tier': 'gold'},
  { 'badges': ['Gold Clamps', 'Gold Menace', 'Silver Dimer'],
    'id': 'gold-jrue-83',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/2/23/Jrue_Holiday_2024.jpg',
    'name': 'Jrue Holiday',
    'ovr': 83,
    'pos': 'PG',
    'quote': '2x NBA Champion • 6x All-Defensive Team • The Guard Stopper',
    'sec_pos': 'SG',
    'stats': {'3pt': 80, 'ath': 81, 'clu': 86, 'def': 91, 'ins': 82, 'ply': 84},
    'team': 'BOS',
    'theme': 'Championship Anchor',
    'tier': 'gold'},
  { 'badges': ['Gold Clamps', 'Gold Interceptor', 'Silver Corner Specialist'],
    'id': 'gold-anunoby-82',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/b/b3/OG_Anunoby_2020.jpg',
    'name': 'OG Anunoby',
    'ovr': 82,
    'pos': 'SF',
    'quote': 'NBA Steals Leader • All-Defensive Team • Versatile Stopper',
    'sec_pos': 'PF',
    'stats': {'3pt': 80, 'ath': 84, 'clu': 80, 'def': 89, 'ins': 82, 'ply': 72},
    'team': 'NYK',
    'theme': 'Lockdown Wing',
    'tier': 'gold'},
  { 'badges': ['Gold Pick Dodger', 'Silver Clamps', 'Silver Catch & Shoot'],
    'id': 'gold-mikal-82',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/eb/Mikal_Bridges_2022.jpg',
    'name': 'Mikal Bridges',
    'ovr': 82,
    'pos': 'SF',
    'quote': 'Never Misses a Game • Elite Wing Defense • Knockdown Shooter',
    'sec_pos': 'SG',
    'stats': {'3pt': 82, 'ath': 82, 'clu': 81, 'def': 86, 'ins': 79, 'ply': 76},
    'team': 'NYK',
    'theme': 'Iron Man Wing',
    'tier': 'gold'},
  { 'badges': ['Gold Anchor', 'Gold Floor General', 'Gold Post Lockdown'],
    'id': 'gold-draymond-82',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/1/1b/Draymond_Green_2022.jpg',
    'name': 'Draymond Green',
    'ovr': 82,
    'pos': 'PF',
    'quote': '4x NBA Champion • 2017 DPOY • 8x All-Defensive Team',
    'sec_pos': 'C',
    'stats': {'3pt': 70, 'ath': 78, 'clu': 85, 'def': 92, 'ins': 76, 'ply': 86},
    'team': 'GSW',
    'theme': 'Defensive General',
    'tier': 'gold'},
  { 'badges': ['Gold Chase Down Artist', 'Silver Clamps', 'Silver Catch & Shoot'],
    'id': 'gold-white-82',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/4b/Derrick_White_2022.jpg',
    'name': 'Derrick White',
    'ovr': 82,
    'pos': 'PG',
    'quote': '2024 NBA Champion • 2x All-Defensive Team • Ultimate Two-Way Guard',
    'sec_pos': 'SG',
    'stats': {'3pt': 83, 'ath': 78, 'clu': 85, 'def': 88, 'ins': 77, 'ply': 82},
    'team': 'BOS',
    'theme': 'Championship Guard',
    'tier': 'gold'},
  { 'badges': ['Silver Dimer', 'Silver Space Creator', 'Silver Acrobat'],
    'id': 'gold-reaves-82',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/e0/Austin_Reaves_2023.jpg',
    'name': 'Austin Reaves',
    'ovr': 82,
    'pos': 'SG',
    'quote': 'Playoff Proven Playmaker • Crafty Finisher • Fan Favorite',
    'sec_pos': 'PG',
    'stats': {'3pt': 82, 'ath': 76, 'clu': 84, 'def': 74, 'ins': 80, 'ply': 84},
    'team': 'LAL',
    'theme': 'Lakers Sparkplug',
    'tier': 'gold'},
  { 'badges': ['Gold Posterizer', 'Gold Brick Wall', 'Silver Rebound Chaser'],
    'id': 'gold-gordon-82',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/3/30/Aaron_Gordon_2020.jpg',
    'name': 'Aaron Gordon',
    'ovr': 82,
    'pos': 'PF',
    'quote': '2023 NBA Champion • High-Flying Dunker • Physical Defender',
    'sec_pos': 'SF',
    'stats': {'3pt': 70, 'ath': 90, 'clu': 82, 'def': 84, 'ins': 88, 'ply': 75},
    'team': 'DEN',
    'theme': 'Mile High Enforcer',
    'tier': 'gold'},
  { 'badges': ['Gold Glove', 'Silver Dimer', 'Silver Fast Break Starter'],
    'id': 'gold-iggy-81',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/3/36/Andre_Iguodala_2016.jpg',
    'name': 'Andre Iguodala',
    'ovr': 81,
    'pos': 'SF',
    'quote': '4x NBA Champion • 2015 Finals MVP • Defensive Mastermind',
    'sec_pos': 'SG',
    'stats': {'3pt': 75, 'ath': 80, 'clu': 84, 'def': 88, 'ins': 80, 'ply': 80},
    'team': 'GSW',
    'theme': 'Dynasty Veteran',
    'tier': 'gold'},
  { 'badges': ['Gold Clamps', 'Gold Pick Dodger', 'Silver Interceptor'],
    'id': 'gold-caruso-81',
    'image_url': 'https://upload.wikimedia.org/wikipedia/commons/2/29/Alex_Caruso_%2851888062828%29_%28cropped%29.jpg',
    'name': 'Alex Caruso',
    'ovr': 81,
    'pos': 'SG',
    'quote': 'All-Defensive First Team • Championship Glue Guy • Elite PoA Lock',
    'sec_pos': 'PG',
    'stats': {'3pt': 78, 'ath': 82, 'clu': 80, 'def': 89, 'ins': 76, 'ply': 80},
    'team': 'OKC',
    'theme': 'Defensive Menace',
    'tier': 'gold'}]

NBA_PACK_TYPES = { 'allstar': { 'color': 2718207,
               'cost': 1500,
               'description': 'High-value pack packed with Ruby/Amethyst stars, Diamonds, and Galaxy Opals.',
               'icon': '⭐',
               'id': 'allstar',
               'name': '⭐ All-Star Gold Pack',
               'odds': {'amethyst': 0.35, 'diamond': 0.2, 'galaxy_opal': 0.05, 'ruby': 0.4}},
  'boss_raid': { 'color': 16717636,
                 'cost': 0,
                 'description': 'Exclusive raid participant pack loaded with Diamond, Galaxy Opal, and Dark Matter '
                                'rewards!',
                 'icon': '👑',
                 'id': 'boss_raid',
                 'name': '👑 Boss Raid Victory Pack',
                 'odds': {'dark_matter': 0.2, 'diamond': 0.4, 'galaxy_opal': 0.4}},
  'goat': { 'color': 8069026,
            'cost': 5000,
            'description': 'Ultra-premium pack featuring only Diamond, Galaxy Opal, and 99 OVR Dark Matter legends!',
            'icon': '🐐',
            'id': 'goat',
            'name': '🐐 G.O.A.T. Dynasty Pack',
            'odds': {'dark_matter': 0.25, 'diamond': 0.35, 'galaxy_opal': 0.4}},
  'hof': { 'color': 11225020,
           'cost': 3000,
           'description': 'Elite pack boasting heavy Diamond, Galaxy Opal, and high Dark Matter pull rates.',
           'icon': '🏆',
           'id': 'hof',
           'name': '🏆 Hall of Fame Elite Pack',
           'odds': {'amethyst': 0.3, 'dark_matter': 0.05, 'diamond': 0.45, 'galaxy_opal': 0.2}},
  'standard': { 'color': 15094016,
                'cost': 750,
                'description': 'Balanced pack featuring solid odds for Gold, Ruby, Amethyst, and a shot at Diamond.',
                'icon': '🏀',
                'id': 'standard',
                'name': '🏀 Standard Pro Pack',
                'odds': {'amethyst': 0.12, 'diamond': 0.03, 'gold': 0.5, 'ruby': 0.35}},
  'starter': { 'color': 16766720,
               'cost': 250,
               'description': 'Affordable entry pack with guaranteed Gold/Ruby cards and a chance at Amethyst.',
               'icon': '📦',
               'id': 'starter',
               'name': '📦 Starter Pack',
               'odds': {'amethyst': 0.05, 'gold': 0.7, 'ruby': 0.25}}}

NBA_CARDS_BY_ID: Dict[str, Dict[str, Any]] = {c["id"].lower(): c for c in NBA_2K_MOBILE_CARDS}
for _legacy_k, _canon_k in NBA_LEGACY_CARD_MAPPINGS.items():
    if _canon_k.lower() in NBA_CARDS_BY_ID:
        NBA_CARDS_BY_ID[_legacy_k.lower()] = NBA_CARDS_BY_ID[_canon_k.lower()]

NBA_TIER_QUERY_ALIASES = [ ('exclusive', ['exclusive', 'excl', '1of1']),
  ('dark_matter', ['dark matter', 'darkmatter', 'dm', 'black']),
  ('galaxy_opal', ['galaxy opal', 'galaxyopal', 'opal', 'go']),
  ('diamond', ['diamond', 'dia', 'cyan', 'blue']),
  ('amethyst', ['amethyst', 'amy', 'amethist', 'purple']),
  ('ruby', ['ruby', 'rubie', 'red']),
  ('gold', ['gold', 'emerald', 'yellow', 'green'])]

NBA_REAL_MOMENTS = { 'amy-aedwards-90': 'Ant- ManRising •',
  'amy-billwalton-91': 'All- StarPerformer• ( 2x) •',
  'amy-brown-91': 'FinalsMVP •',
  'amy-brunson-92': 'GardenMVP •',
  'amy-chet-89': 'Shot- BlockingPhenom •',
  'amy-chetholmgren-89': 'All- StarPerformer• ( 1x) •',
  'amy-fox-90': 'InauguralClutchPOTY •',
  'amy-jalen-89': 'MSGMaestro •',
  'amy-jamalmurray-89': 'All- StarPerformer• ( 1x) •',
  'amy-kat-90': '3PTContestChampBig •',
  'amy-lamelo-89': 'FlashyPasser •',
  'amy-lameloball-89': 'All- StarPerformer• ( 1x) •',
  'amy-manuginobili-91': 'All- StarPerformer• ( 2x) •',
  'amy-murray-89': 'PlayoffBucket •',
  'amy-paolo-90': 'All- StarPointForward •',
  'amy-paolobanchero-89': 'All- StarPerformer• ( 1x) •',
  'amy-pawlo-89': 'ROYProdigy •',
  'amy-trae-89': 'IceTraeDeep• 3 •',
  'amy-zion-90': 'PaintBulldozer •',
  'dia-adavis-93': 'BrowDominance •',
  'dia-ant-95': 'Ant- ManPosterizer •',
  'dia-anthonyedwards-95': 'FranchiseAll- Star• ( 4x) •',
  'dia-bam-93': 'DPOYFinalist •',
  'dia-bamadebayo-94': 'FranchiseAll- Star• ( 3x) •',
  'dia-blakegriffin-96': 'FranchiseAll- Star• ( 6x) •',
  'dia-booker-94': '70- PtScorer •',
  'dia-dame-94': 'DameTimeClutch •',
  'dia-deaaronfox-93': 'FranchiseAll- Star• ( 2x) •',
  'dia-devinbooker-96': 'FranchiseAll- Star• ( 5x) •',
  'dia-dirk-95': 'One- LegFadeaway •',
  'dia-draymondgreen-95': 'FranchiseAll- Star• ( 4x) •',
  'dia-giannis-94': '2xMVPGreekFreak •',
  'dia-hakeem-96': 'TheDreamShake •',
  'dia-hali-94': 'DimerSpecialist •',
  'dia-jalenbrunson-94': 'FranchiseAll- Star• ( 3x) •',
  'dia-jamorant-93': 'FranchiseAll- Star• ( 2x) •',
  'dia-jaylenbrown-96': 'FranchiseAll- Star• ( 5x) •',
  'dia-jrueholiday-93': 'FranchiseAll- Star• ( 2x) •',
  'dia-karlanthonytowns-96': 'FranchiseAll- Star• ( 6x) •',
  'dia-klaythompson-96': 'FranchiseAll- Star• ( 5x) •',
  'dia-kyrie-95': 'AnkleBreakerMaster •',
  'dia-morant-93': 'GravityDefier •',
  'dia-pennyhardaway-95': 'FranchiseAll- Star• ( 4x) •',
  'dia-sga-95': 'MVPTakeover •',
  'dia-sga-96': 'SmoothMVPFinalist •',
  'dia-shaigilgeousalexander-95': 'FranchiseAll- Star• ( • 4 • x • ) •',
  'dia-spida-94': '71- PtExplosion •',
  'dia-tatum-94': '2024Champion •',
  'dia-traeyoung-95': 'FranchiseAll- Star• ( 4x) •',
  'dia-tyresehaliburton-93': 'FranchiseAll- Star• ( 2x) •',
  'dia-victorwembanyama-93': 'FranchiseAll- Star• ( 2x) •',
  'dia-zionwilliamson-93': 'FranchiseAll- Star• ( 2x) •',
  'dm-billrussell-99': '11xChampionAnchor •',
  'dm-bird-99': 'BostonLegend •',
  'dm-curry-99': 'UnanimousMVP •',
  'dm-giannis-99': 'GreekFreakMVP •',
  'dm-hakeemolajuwon-99': 'TheDreamShake •',
  'dm-jordan-99': '• G • . • O • . • A • . • T • . •   Edition •',
  'dm-kareemabduljabbar-99': 'SkyhookMaster •',
  'dm-kd-99': 'SlimReaper• 3 • - Level •',
  'dm-kobe-99': '81- PtMasterpiece •',
  'dm-kobebryant-99': '81- PtMamba •',
  'dm-larrybird-99': 'BostonLegend •',
  'dm-lebron-98': 'All- TimeScoringKing •',
  'dm-lebron-99': 'InvincibleKing •',
  'dm-lebronjames-99': 'All- TimeScoringKing •',
  'dm-magic-99': 'ShowtimeMaestro •',
  'dm-magicjohnson-99': 'ShowtimeMaestro •',
  'dm-michaeljordan-99': '• G • . • O • . • A • . • T • . •   Edition •',
  'dm-mj-99': '6xChampionSilhouette •',
  'dm-shaq-99': 'DieselDominance •',
  'dm-shaquilleoneal-99': 'DieselDominance •',
  'dm-stephencurry-99': 'UnanimousMVP •',
  'dm-timduncan-99': 'TheBigFundamental •',
  'dm-victorwembanyama-99': 'AlienInvincible •',
  'dm-wemby-99': 'AlienInvincible •',
  'dm-wiltchamberlain-99': '100- PointDominator •',
  'excl-bam-93': '2020ECFGame• 1 •   Game- Savin • g •   Left- HandedRimRejecti ononJaysonTatum •',
  'excl-barkley-96': '1993WesternConference• F inalsGame• 7 •   44- Point24 • - ReboundRoarvsSonics •',
  'excl-bird-98': '19863PTContestLastSho • t •   FingerintheAirBefor • e •   itDropped• & •   JacketOn •',
  'excl-cp3-96': '2021WCFGame• 6 •   41- Point• S econdHalfEruptionatSt aplesCenter •',
  'excl-curry-98': "2022FinalsGame• 6 • ' Night •   Night' •   GesturePointingtoRingFinger •",
  'excl-dirk-97': '2011FinalsGame• 2 •   Left- • H andedGame- WinningDrivin • g •   Layup• & •   TrophyTears •',
  'excl-duncan-98': '2003FinalsGame• 6 •   21PTS • , •   20REB, •   10AST, • 8 •   BLKChampionshipHug •',
  'excl-durant-98': '2017FinalsGame• 3 •   Cold- • B loodedPull- Up• 3 •   OverLe BronJames •',
  'excl-embiid-96': '70- PointMasterpieceCele bration• & •   RoarvsSanAn tonioSpurs •',
  'excl-garnett-97': "2008NBAFinalsGame• 6 • C • o nfettiHug• & • ' ANYTHING• I • S •   POSSIBLE! • ' •   Roar •",
  'excl-giannis-97': '2021FinalsGame• 6 •   50- Poi ntMasterpiece• & •   TrophyKissinMilwaukee •',
  'excl-hakeem-98': '1994FinalsDreamShake• C linicOverPatrickEwing • & •   DavidRobinson •',
  'excl-isiah-96': '1988FinalsGame• 6 •   25- Poi ntSingleQuarteronHeav ilySprainedAnkle •',
  'excl-iverson-97': '2001FinalsGame• 1 •   Corner •   Step- BackJumper• & •   Step overOverTyronnLue •',
  'excl-jerrywest-97': '1970FinalsGame• 3 •   60- Fo otBuzzer- BeatingHalf- • C ourtMiracleShot •',
  'excl-jokic-97': '2023NBAChampionshipPar adeTrophyLift• & •   Celebra toryLaugh •',
  'excl-jordan-99': "1998FinalsGame• 6 • ' The• L astShot' •   OverBryonRus sellfor6thRing •",
  'excl-kareem-99': '1974FinalsGame• 6 •   Iconic •   SkyhookBuzzer- Beater• O verBoston •',
  'excl-kobe-99': '81- PointHistoricMasterp iecevsRaptors• & •   Index• F ingertotheSky •',
  'excl-lebron-99': "2016FinalsGame• 7 • ' The• B lock' •   onAndreIguodala• & •   ChampionshipTears •",
  'excl-luka-96': 'IntentionalMissedFree• T hrowPutbackBuzzer- Beate • r • & •   DancingJigvsKnicks •',
  'excl-magic-99': "1987FinalsGame• 4 • ' Junio • r • , •   Junior' •   SkyhookGame- • W inneratBostonGarden •",
  'excl-oscar-97': '1971FinalsChampionshipCelebrationWithKareem• i • n •   Milwaukee •',
  'excl-pippen-96': '1994ECSFGame• 6 •   Tomahawk •   PosterSlamOverPatric • k •   Ewing• & •   Strut •',
  'excl-russell-98': '1962FinalsGame• 7 •   30Poi nts• & •   40ReboundsChampi onshipClincher •',
  'excl-shaq-99': '2000WCFGame• 7 •   Running• A lley- OopLobfromKobevs •   Blazers •',
  'excl-tatum-95': "2024NBAFinalsGame• 5 •   Cl incher• ' WeDidIt! • ' •   Troph • y •   Scream• & •   Confetti •",
  'excl-tmac-96': '13Pointsin33Seconds• M iracleGame- WinningPull- Up• 3 •   vsSanAntonioSpurs •',
  'excl-vince-94': '2000SlamDunkContestHo neyDipElbow- In- The- Rim• & •   360WindmillSlam •',
  'excl-wade-96': "2006FinalsGame• 3 •   Comeba ckRoar• & •   JumpingonScor er' • s •   Table •",
  'excl-wilkins-95': '1988SlamDunkContest• T • w • o • - HandedBackscratcher• W indmillSlam •',
  'excl-wilt-99': "HoldingtheHand- Written• ' 100' •   PaperSigninHersh eyArenaLockerRoom •",
  'go-ad-97': 'TheBrowAnchor •',
  'go-alleniverson-97': 'TheAnswerCrossover •',
  'go-alonzomourning-97': '2xDPOYPaintProtector •',
  'go-anthonydavis-97': 'TheBrowDefensiveWall •',
  'go-bobcousy-97': 'HoudinioftheHardwood •',
  'go-butler-97': 'PlayoffJimmy •',
  'go-carmeloanthony-97': 'OlympicGold• & •   62- PtMS • G •',
  'go-charlesbarkley-98': 'RoundMoundofRebound •',
  'go-chrispaul-97': 'PointGodFloorGeneral •',
  'go-clydedrexler-98': 'HallofFameLegend• ( 10x •   All- Star) •',
  'go-curry-97': 'GreatestShooterEver •',
  'go-damianlillard-98': 'HallofFameLegend• ( 9x •   All- Star) •',
  'go-davidrobinson-98': 'TheAdmiralQuadruple- • D • o uble •',
  'go-dikembemutombo-97': 'FingerWag4xDPOY •',
  'go-dirknowitzki-98': 'One- LegFadeawayRing •',
  'go-dominiquewilkins-98': 'HallofFameLegend• ( • 9 • x •   All- Star) •',
  'go-donovanmitchell-97': 'HallofFameLegend• ( 7x •   All- Star) •',
  'go-duncan-98': 'TheBigFundamental •',
  'go-durant-96': 'SlimReaper •',
  'go-dwighthoward-97': 'HallofFameLegend• ( 8x •   All- Star) •',
  'go-dwyanewade-98': 'FlashFinalsMVP •',
  'go-elginbaylor-98': 'AcrobaticPioneer •',
  'go-embiid-98': 'ProcessMVP •',
  'go-garypayton-97': 'TheGloveDPOYGuard •',
  'go-giannisantetokounmpo-98': 'GreekFreakDominance •',
  'go-granthill-97': 'PointForwardPhenom •',
  'go-isiahthomas-98': 'BadBoysGeneral •',
  'go-iverson-97': 'TheAnswer •',
  'go-jamesharden-97': 'TheStepbackMVP •',
  'go-jasonkidd-98': 'Triple- DoubleGeneral •',
  'go-jaysontatum-98': '2024ChampionWing •',
  'go-jerrywest-98': 'TheNBALogo •',
  'go-jimmybutler-97': 'PlayoffJimmyEnforcer •',
  'go-joelembiid-98': '70- PtMVPProcess •',
  'go-johnstockton-98': 'All- TimeAssistKing •',
  'go-jokic-97': '3xMVPMaestro •',
  'go-jokic-98': 'PointCenterGenius •',
  'go-juliuserving-98': 'Dr. • J •   AbovetheRim •',
  'go-karlmalone-98': 'TheMailmanPick• & •   Roll •',
  'go-kawhi-97': 'TheClawLock •',
  'go-kawhileonard-97': 'TheClawLockdown •',
  'go-kevindurant-98': 'SlimReaper• 3 • - Level •',
  'go-kevingarnett-98': 'TheBigTicket •',
  'go-kyrieirving-98': 'HallofFameLegend• ( 9xAll- Star) •',
  'go-luka-98': 'TripleDoubleKing •',
  'go-lukadoncic-98': '60- PtTriple- DoubleKing •',
  'go-mosesmalone-98': 'ChairmanoftheBoards •',
  'go-nikolajokic-98': '3xMVPPointCenter •',
  'go-oscarrobertson-98': 'TheBig• O •   Triple- Double •',
  'go-patrickewing-98': 'HallofFameLegend• ( 11x •   All- Star) •',
  'go-paulgeorge-98': 'HallofFameLegend• ( 9xAll- Star) •',
  'go-paulpierce-97': 'TheTruthFinalsMVP •',
  'go-petemaravich-97': 'HallofFameLegend• ( 5x •   All- Star) •',
  'go-rayallen-97': 'Game• 6 •   CornerMiracle •',
  'go-reggiemiller-97': '• 8 •   Pointsin• 9 •   Seconds •',
  'go-rickbarry-97': 'HallofFameLegend• ( 8x• A ll- Star) •',
  'go-russellwestbrook-97': 'Triple- DoubleSeason• M • V • P •',
  'go-scottiepippen-98': '6xChampionLockdown •',
  'go-stevenash-98': '• 7 •   SecondsorLessMVP •',
  'go-tatum-98': 'FinalsChampion •',
  'go-timhardaway-97': 'HallofFameLegend• ( 5xAll- Star) •',
  'go-tmac-98': '13in35s •',
  'go-tonyparker-97': '2007FinalsMVPTeardrop •',
  'go-tracymcgrady-98': '13Pointsin33Seconds •',
  'go-vincecarter-97': 'Half- ManHalf- Amazing •',
  'go-waltfrazier-98': 'Clyde1970Finals36- 19 •',
  'go-willisreed-97': 'HallofFameLegend• ( 7xAll- Star) •',
  'gold-alexcaruso-81': 'StealsSpecialist •',
  'gold-anunoby-82': 'Lockdown Wing',
  'gold-caruso-81': 'Defensive Menace',
  'gold-cp3-82': 'Point God',
  'gold-draymond-82': 'Defensive General',
  'gold-ginobili-83': 'Eurostep Maestro',
  'gold-gordon-82': 'Mile High Enforcer',
  'gold-grant-82': 'Veteran Rebirth',
  'gold-iggy-81': 'Dynasty Veteran',
  'gold-jrue-83': 'Championship Anchor',
  'gold-klay-83': 'Splash Brother',
  'gold-mikal-82': 'Iron Man Wing',
  'gold-parker-83': 'French Tear Drop',
  'gold-reaves-82': 'Lakers Sparkplug',
  'gold-westbrook-82': 'Relentless Motor',
  'gold-white-82': 'Championship Guard',
  'ruby-aarongordon-85': 'DunkContestKing •',
  'ruby-andreiguodala-84': 'All- StarStandout• ( 2012 • ) •',
  'ruby-anunoby-85': 'DefensiveMenace •',
  'ruby-austinreaves-84': 'CraftyPlaymaker •',
  'ruby-derrickwhite-86': 'Two- WayGlue •',
  'ruby-gordon-85': 'DunkContestKing •',
  'ruby-green-84': 'Defensive Anchor',
  'ruby-jrue-86': '2xChampionClamp •',
  'ruby-mikal-85': 'IronManLock •',
  'ruby-mikalbridges-85': 'IronManLock •',
  'ruby-oganunoby-85': 'DefensiveMenace •',
  'ruby-reaves-84': 'CraftyPlaymaker •',
  'ruby-trae-87': 'IceTraeMaestro •',
  'ruby-wemby-88': 'AlienProdigy •',
  'ruby-white-86': 'Two- WayGlue •',
  'ruby-zion-86': 'ZionFreightTrain •'}

NBA_DREAM_PLAYERS = { 'C': [ { 'archetype': 'Dominant Bully Big',
           'blocked': ['three'],
           'clutch': 95,
           'cost': 5,
           'defense': 93,
           'emoji': '💥',
           'favored': ['drive', 'defense'],
           'inside': 99,
           'name': "Shaquille O'Neal",
           'playmaking': 72,
           'pts_3': 50,
           'tag': '3x Finals MVP • Most Dominant Force',
           'team': 'LAL'},
         { 'archetype': 'Post Footwork Genius',
           'blocked': ['three'],
           'clutch': 97,
           'cost': 4,
           'defense': 99,
           'emoji': '🌪️',
           'favored': ['defense', 'iso', 'drive'],
           'inside': 98,
           'name': 'Hakeem Olajuwon',
           'playmaking': 82,
           'pts_3': 62,
           'tag': '2x DPOY • The Dream Shake',
           'team': 'HOU'},
         { 'archetype': 'Post Playmaker & Touch Scorer',
           'blocked': ['defense'],
           'clutch': 97,
           'cost': 3,
           'defense': 79,
           'emoji': '🃏',
           'favored': ['pnr', 'drive', 'three'],
           'inside': 97,
           'name': 'Nikola Jokić',
           'playmaking': 99,
           'pts_3': 87,
           'tag': '3x MVP • Triple-Double Magician',
           'team': 'DEN'},
         { 'archetype': 'Rim-Running Monster',
           'blocked': ['three'],
           'clutch': 94,
           'cost': 2,
           'defense': 97,
           'emoji': '🦌',
           'favored': ['drive', 'defense', 'pnr'],
           'inside': 99,
           'name': 'Giannis Antetokounmpo',
           'playmaking': 86,
           'pts_3': 68,
           'tag': '2x MVP • Greek Freak Freight Train',
           'team': 'MIL'},
         { 'archetype': 'Alien Rim Anchor',
           'blocked': ['drive'],
           'clutch': 90,
           'cost': 1,
           'defense': 98,
           'emoji': '👽',
           'favored': ['defense', 'three', 'pnr'],
           'inside': 91,
           'name': 'Victor Wembanyama',
           'playmaking': 78,
           'pts_3': 84,
           'tag': '7ft 4in • Alien Shot-Blocker',
           'team': 'SAS'}],
  'PF': [ { 'archetype': 'Interior Anchor & Bank Shot',
            'blocked': ['three'],
            'clutch': 97,
            'cost': 5,
            'defense': 99,
            'emoji': '🏛️',
            'favored': ['drive', 'defense', 'pnr'],
            'inside': 98,
            'name': 'Tim Duncan',
            'playmaking': 84,
            'pts_3': 60,
            'tag': '5x Champ • The Big Fundamental',
            'team': 'SAS'},
          { 'archetype': 'Clutch Point Forward',
            'blocked': [],
            'clutch': 99,
            'cost': 4,
            'defense': 87,
            'emoji': '🍀',
            'favored': ['three', 'pnr', 'iso'],
            'inside': 89,
            'name': 'Larry Bird',
            'playmaking': 95,
            'pts_3': 94,
            'tag': '3x MVP • Legendary Trash Talker',
            'team': 'BOS'},
          { 'archetype': 'One-Leg Fadeaway Specialist',
            'blocked': ['defense', 'drive'],
            'clutch': 98,
            'cost': 3,
            'defense': 79,
            'emoji': '🇩🇪',
            'favored': ['iso', 'three'],
            'inside': 93,
            'name': 'Dirk Nowitzki',
            'playmaking': 79,
            'pts_3': 95,
            'tag': 'Finals MVP • Unblockable Fadeaway',
            'team': 'DAL'},
          { 'archetype': 'Lob Threat & Shot-Blocker',
            'blocked': ['three'],
            'clutch': 92,
            'cost': 2,
            'defense': 97,
            'emoji': '〰️',
            'favored': ['drive', 'defense', 'pnr'],
            'inside': 97,
            'name': 'Anthony Davis',
            'playmaking': 78,
            'pts_3': 76,
            'tag': 'NBA Champ • The Brow Two-Way Anchor',
            'team': 'LAL'},
          { 'archetype': 'Stretch Big',
            'blocked': ['defense'],
            'clutch': 88,
            'cost': 1,
            'defense': 84,
            'emoji': '🐺',
            'favored': ['three', 'drive'],
            'inside': 90,
            'name': 'Naz Reid',
            'playmaking': 74,
            'pts_3': 88,
            'tag': '6th Man of the Year • Fan Favorite Sniper',
            'team': 'MIN'}],
  'PG': [ { 'archetype': 'Sniper Specialist',
            'blocked': ['defense'],
            'clutch': 98,
            'cost': 5,
            'defense': 78,
            'emoji': '🎯',
            'favored': ['three', 'pnr'],
            'inside': 84,
            'name': 'Stephen Curry',
            'playmaking': 92,
            'pts_3': 99,
            'tag': 'Unanimous MVP • Greatest Shooter Ever',
            'team': 'GSW'},
          { 'archetype': 'Explosive Combo Guard',
            'blocked': [],
            'clutch': 97,
            'cost': 5,
            'defense': 95,
            'emoji': '⚡',
            'favored': ['iso', 'three', 'drive', 'pnr'],
            'inside': 95,
            'name': 'Ryan Rollins',
            'playmaking': 98,
            'pts_3': 97,
            'tag': '99 OVR • Breakout Invincible',
            'team': 'MIL'},
          { 'archetype': 'Showtime Floor General',
            'blocked': ['three'],
            'clutch': 96,
            'cost': 4,
            'defense': 86,
            'emoji': '🪄',
            'favored': ['pnr', 'drive'],
            'inside': 92,
            'name': 'Magic Johnson',
            'playmaking': 99,
            'pts_3': 78,
            'tag': '5x Champ • Showtime Maestro',
            'team': 'LAL'},
          { 'archetype': 'Mid-Range General',
            'blocked': [],
            'clutch': 94,
            'cost': 3,
            'defense': 94,
            'emoji': '🧠',
            'favored': ['pnr', 'defense', 'iso'],
            'inside': 80,
            'name': 'Chris Paul',
            'playmaking': 96,
            'pts_3': 86,
            'tag': 'Point God • Floor General',
            'team': 'LAC'},
          { 'archetype': 'Isolation Wizard',
            'blocked': ['defense'],
            'clutch': 98,
            'cost': 2,
            'defense': 76,
            'emoji': '⚡',
            'favored': ['iso', 'three', 'drive'],
            'inside': 96,
            'name': 'Kyrie Irving',
            'playmaking': 88,
            'pts_3': 92,
            'tag': 'Ankle Breaker • Finals Dagger',
            'team': 'CLE'},
          { 'archetype': 'Perimeter Lock',
            'blocked': ['iso'],
            'clutch': 90,
            'cost': 1,
            'defense': 97,
            'emoji': '🔒',
            'favored': ['defense', 'pnr'],
            'inside': 82,
            'name': 'Jrue Holiday',
            'playmaking': 86,
            'pts_3': 85,
            'tag': '2x Champ • Perimeter Clamp',
            'team': 'BOS'}],
  'SF': [ { 'archetype': 'All-Around Point Forward',
            'blocked': [],
            'clutch': 97,
            'cost': 5,
            'defense': 95,
            'emoji': '👑',
            'favored': ['drive', 'pnr', 'defense', 'iso'],
            'inside': 99,
            'name': 'LeBron James',
            'playmaking': 99,
            'pts_3': 85,
            'tag': '4x MVP • All-Around King',
            'team': 'MIA'},
          { 'archetype': 'Generational 3&D Wing',
            'blocked': [],
            'clutch': 96,
            'cost': 5,
            'defense': 98,
            'emoji': '⭐',
            'favored': ['drive', 'three', 'defense', 'pnr'],
            'inside': 98,
            'name': 'Carter Bryant',
            'playmaking': 94,
            'pts_3': 95,
            'tag': '99 OVR • Next Gen Invincible',
            'team': 'SAS'},
          { 'archetype': 'Lockdown Finals MVP',
            'blocked': [],
            'clutch': 98,
            'cost': 4,
            'defense': 99,
            'emoji': '🔒',
            'favored': ['defense', 'drive', 'pnr'],
            'inside': 95,
            'name': 'Andre Iguodala (2015)',
            'playmaking': 93,
            'pts_3': 90,
            'tag': '97 OVR • 2015 Finals MVP',
            'team': 'GSW'},
          { 'archetype': 'Unblockable 3-Level Scorer',
            'blocked': [],
            'clutch': 97,
            'cost': 4,
            'defense': 89,
            'emoji': '🎯',
            'favored': ['three', 'iso', 'drive'],
            'inside': 94,
            'name': 'Kevin Durant',
            'playmaking': 85,
            'pts_3': 95,
            'tag': '2x Finals MVP • 7ft Walking Bucket',
            'team': 'GSW'},
          { 'archetype': 'Lockdown Two-Way Force',
            'blocked': [],
            'clutch': 97,
            'cost': 3,
            'defense': 99,
            'emoji': '🤖',
            'favored': ['defense', 'iso', 'three'],
            'inside': 91,
            'name': 'Kawhi Leonard',
            'playmaking': 82,
            'pts_3': 89,
            'tag': '2x DPOY • The Klaw Lock',
            'team': 'TOR'},
          { 'archetype': 'Playoff Enforcer',
            'blocked': [],
            'clutch': 98,
            'cost': 2,
            'defense': 94,
            'emoji': '☕',
            'favored': ['drive', 'defense', 'iso'],
            'inside': 92,
            'name': 'Jimmy Butler',
            'playmaking': 86,
            'pts_3': 80,
            'tag': 'Playoff Jimmy • Clutch Beast',
            'team': 'MIA'},
          { 'archetype': 'Perimeter Disrupter',
            'blocked': ['iso', 'drive'],
            'clutch': 87,
            'cost': 1,
            'defense': 95,
            'emoji': '🦅',
            'favored': ['defense', 'pnr'],
            'inside': 78,
            'name': 'Alex Caruso',
            'playmaking': 80,
            'pts_3': 82,
            'tag': 'All-Defensive • Steal & Hustle Master',
            'team': 'OKC'}],
  'SG': [ { 'archetype': 'Two-Way GOAT',
            'blocked': [],
            'clutch': 99,
            'cost': 5,
            'defense': 99,
            'emoji': '🐐',
            'favored': ['iso', 'drive', 'defense'],
            'inside': 99,
            'name': 'Michael Jordan',
            'playmaking': 88,
            'pts_3': 82,
            'tag': '6x Finals MVP • Undisputed GOAT',
            'team': 'CHI'},
          { 'archetype': 'Flamethrower Sniper',
            'blocked': [],
            'clutch': 99,
            'cost': 5,
            'defense': 96,
            'emoji': '🔥',
            'favored': ['three', 'defense'],
            'inside': 92,
            'name': 'Klay Thompson (2016)',
            'playmaking': 85,
            'pts_3': 99,
            'tag': '98 OVR • 37-Point Quarter',
            'team': 'GSW'},
          { 'archetype': 'Mamba Shot-Maker',
            'blocked': [],
            'clutch': 99,
            'cost': 4,
            'defense': 96,
            'emoji': '🐍',
            'favored': ['iso', 'drive', 'defense'],
            'inside': 96,
            'name': 'Kobe Bryant',
            'playmaking': 86,
            'pts_3': 86,
            'tag': '5x Champ • Mamba Mentality',
            'team': 'LAL'},
          { 'archetype': 'Slashing Guard',
            'blocked': ['three'],
            'clutch': 96,
            'cost': 3,
            'defense': 93,
            'emoji': '⚡',
            'favored': ['drive', 'pnr', 'defense'],
            'inside': 97,
            'name': 'Dwyane Wade',
            'playmaking': 90,
            'pts_3': 76,
            'tag': '3x Champ • Finals MVP Slashing Flash',
            'team': 'MIA'},
          { 'archetype': '3-and-D Sniper',
            'blocked': ['drive', 'iso'],
            'clutch': 95,
            'cost': 2,
            'defense': 92,
            'emoji': '🔥',
            'favored': ['three', 'defense'],
            'inside': 78,
            'name': 'Klay Thompson',
            'playmaking': 74,
            'pts_3': 98,
            'tag': '4x Champ • Catch & Shoot Flamethrower',
            'team': 'GSW'},
          { 'archetype': 'Two-Way Glue',
            'blocked': ['iso'],
            'clutch': 88,
            'cost': 1,
            'defense': 93,
            'emoji': '🦬',
            'favored': ['defense', 'three'],
            'inside': 80,
            'name': 'Derrick White',
            'playmaking': 82,
            'pts_3': 87,
            'tag': 'All-Defensive • Ultimate Glue Guy',
            'team': 'BOS'}]}

NBA_RIVALRIES = { frozenset({'Michael Jordan', 'Kobe Bryant'}): 'Two assassins with identical killer instincts. Only one walks out '
                                                'with the bucket.',
  frozenset({"Shaquille O'Neal", 'Hakeem Olajuwon'}): 'The Diesel vs The Dream. Clash of titanic low-post titans!',
  frozenset({'Klay Thompson', 'Stephen Curry'}): 'Splash Brothers on opposite sides of the hardwood tonight!',
  frozenset({'Kevin Durant', 'LeBron James'}): 'The King vs The Slim Reaper. Pure heavyweight cinema on the wing.',
  frozenset({'Kawhi Leonard', 'LeBron James'}): 'The King meets The Klaw. Every single possession is contested war.',
  frozenset({'Dirk Nowitzki', 'Tim Duncan'}): 'The Big Fundamental vs The Flamingo Fadeaway. Texas legends collide!',
  frozenset({'Larry Bird', 'Magic Johnson'}): 'Showtime vs Boston Pride. The rivalry that built the modern NBA!',
  frozenset({'Stephen Curry', 'Kyrie Irving'}): 'Finals Rematch! Unrivaled handles vs the greatest shooter in history.',
  frozenset({'Giannis Antetokounmpo', 'Anthony Davis'}): 'Greek Freak vs The Brow! Two alien rim-running monsters '
                                                         'collide.',
  frozenset({"Shaquille O'Neal", 'Victor Wembanyama'}): "325-lb Diesel Power meets the 7'4 Modern Alien Anchor!",
  frozenset({'Kobe Bryant', 'Dwyane Wade'}): 'The Black Mamba vs The Flash. Pure elite shooting guard war.',
  frozenset({'Chris Paul', 'Stephen Curry'}): 'Point God chess vs Deep-Range chaos. A decade-long rivalry!',
  frozenset({'LeBron James', 'Jimmy Butler'}): 'Playoff Jimmy goes toe-to-toe with King James in a grueling dogfight!',
  frozenset({'Michael Jordan', 'Klay Thompson'}): 'The GOAT attacks the ultimate 3-and-D perimeter clamp!',
  frozenset({'Chris Paul', 'Magic Johnson'}): 'Showtime flair vs Surgical Point God orchestration!',
  frozenset({'Nikola Jokić', "Shaquille O'Neal"}): 'Sombor Magic Touch vs Low-Post Bully Diesel Force!',
  frozenset({'Kevin Durant', 'Larry Bird'}): 'Cold-blooded trash talk vs unblockable 7-foot silk shooting!',
  frozenset({'Hakeem Olajuwon', 'Victor Wembanyama'}): '8-foot wingspan Alien vs The Master of the Dream Shake!',
  frozenset({'Derrick White', 'Alex Caruso'}): 'The Buffalo vs The Carushow — Ultimate Hustle War!',
  frozenset({'Naz Reid', 'Dirk Nowitzki'}): 'Cult Hero Naz Reid vs The European Trailblazer!'}

GM_RANKS = [ {'icon': '🥉', 'max_wins': 2, 'min_wins': 0, 'name': 'Rookie GM', 'next': 'Starter GM', 'next_wins': 3},
  {'icon': '🥈', 'max_wins': 6, 'min_wins': 3, 'name': 'Starter GM', 'next': 'Role Player GM', 'next_wins': 7},
  {'icon': '🥇', 'max_wins': 14, 'min_wins': 7, 'name': 'Role Player GM', 'next': 'All-Star GM', 'next_wins': 15},
  {'icon': '⭐', 'max_wins': 24, 'min_wins': 15, 'name': 'All-Star GM', 'next': 'MVP GM', 'next_wins': 25},
  {'icon': '👑', 'max_wins': 49, 'min_wins': 25, 'name': 'MVP GM', 'next': 'Hall of Famer GM', 'next_wins': 50},
  {'icon': '🏛️', 'max_wins': 999999, 'min_wins': 50, 'name': 'Hall of Famer GM', 'next': 'MAX RANK', 'next_wins': 50}]

DAILY_BOSS_PRESETS = [ { 'desc': 'Old-school hard-nosed defense paired with explosive transition firepower.',
    'picks': { 'C': 'Hakeem Olajuwon',
               'PF': 'Naz Reid',
               'PG': 'Magic Johnson',
               'SF': 'Alex Caruso',
               'SG': 'Michael Jordan'},
    'title': '90s Physicality & Showtime'},
  { 'desc': 'Unrivaled perimeter shooting flanked by elite wing stoppers.',
    'picks': { 'C': 'Nikola Jokić',
               'PF': 'Anthony Davis',
               'PG': 'Stephen Curry',
               'SF': 'Kawhi Leonard',
               'SG': 'Klay Thompson'},
    'title': 'Splash & Clamp Dynasty'},
  { 'desc': 'Total versatility with 7-foot shot creation and lock-down point-of-attack guards.',
    'picks': { 'C': "Shaquille O'Neal",
               'PF': 'Dirk Nowitzki',
               'PG': 'Jrue Holiday',
               'SF': 'Kevin Durant',
               'SG': 'Derrick White'},
    'title': 'Modern Positionless Juggernaut'},
  { 'desc': 'LeBron James surrounded by elite rim protectors and dead-eye snipers.',
    'picks': { 'C': 'Victor Wembanyama',
               'PF': 'Naz Reid',
               'PG': 'Chris Paul',
               'SF': 'LeBron James',
               'SG': 'Kobe Bryant'},
    'title': "All-Around King's Court"},
  { 'desc': 'Suffocating interior defense with unguardable isolation shotmaking.',
    'picks': { 'C': 'Giannis Antetokounmpo',
               'PF': 'Tim Duncan',
               'PG': 'Kyrie Irving',
               'SF': 'Jimmy Butler',
               'SG': 'Kobe Bryant'},
    'title': 'Twin Towers & Mamba Grit'},
  { 'desc': 'Ultimate basketball IQ, clutch gene shotmakers, and ruthless competitive fire.',
    'picks': {'C': 'Nikola Jokić', 'PF': 'Larry Bird', 'PG': 'Chris Paul', 'SF': 'Jimmy Butler', 'SG': 'Dwyane Wade'},
    'title': "Larry's Clutch Collective"},
  { 'desc': 'Lightning fastbreak transition combined with historic shot-blocking length.',
    'picks': { 'C': 'Victor Wembanyama',
               'PF': 'Tim Duncan',
               'PG': 'Stephen Curry',
               'SF': 'Alex Caruso',
               'SG': 'Dwyane Wade'},
    'title': 'Alien Defense & Flash Explosion'}]

IGNORED_DROP_CHANNEL_KEYWORDS = { 'admin',
  'announcement',
  'announcements',
  'appeals',
  'audit',
  'bot-log',
  'bot-logs',
  'dev',
  'goodbye',
  'guidelines',
  'info',
  'landing',
  'leave',
  'leaves',
  'log',
  'logs',
  'mod',
  'mod-log',
  'mod-logs',
  'mods',
  'owner',
  'private',
  'reaction-roles',
  'roles',
  'rules',
  'secret',
  'staff',
  'strike-appeal',
  'ticket',
  'tickets',
  'verification',
  'verify',
  'welcome'}

_NBA_HEADSHOT_CACHE = LRUImageCache(max_size=15)
_NBA_MOMENT_PHOTO_CACHE = LRUImageCache(max_size=30)
_CARD_GRAPHIC_CACHE: Dict[str, bytes] = {}


def normalize_nba_text(text: str) -> str:
    """Removes accents, punctuation, spaces and lowercases."""
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', text)
    cleaned = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r'[^a-zA-Z0-9]', '', cleaned).lower()


def is_correct_player_name(guess: str, actual_name: str) -> bool:
    """Checks if guess matches full name, last name, or known nicknames."""
    g_norm = normalize_nba_text(guess)
    a_norm = normalize_nba_text(actual_name)
    if not g_norm:
        return False
    if g_norm == a_norm:
        return True
    parts = actual_name.split()
    if len(parts) >= 2:
        last_norm = normalize_nba_text(parts[-1])
        if g_norm == last_norm and len(g_norm) >= 3:
            return True
    aliases = PLAYER_NICKNAMES.get(actual_name, [])
    for alias in aliases:
        if g_norm == normalize_nba_text(alias):
            return True
    return False


def generate_player_hint(name: str, hint_level: int = 1) -> str:
    """Generates a progressive masked hint like 'S _ e _ h e n   C _ r r y'."""
    words = name.split()
    revealed_words = []
    for w in words:
        chars = list(w)
        out = []
        reveal_step = max(1, 4 - hint_level)
        for i, c in enumerate(chars):
            if not c.isalnum():
                out.append(c)
            elif i % reveal_step == 0 or i == 0:
                out.append(c)
            else:
                out.append(r"\_")
        revealed_words.append(" ".join(out))
    return "   ".join(revealed_words)


def _get_nba_card_font(size: int, bold: bool = False):
    """Loads a high-compatibility font for the 2D court card with cross-platform fallbacks."""
    font_candidates = (
        ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial-Bold.ttf", "LiberationSans-Bold.ttf", "arial.ttf", "DejaVuSans.ttf"]
        if bold else
        ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"]
    )
    for font_name in font_candidates:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _draw_star_polygon(draw: ImageDraw.Draw, center: Tuple[int, int], size: int, color: Tuple[int, int, int, int]):
    """Draws a crisp gold star polygon on PIL canvas."""
    cx, cy = center
    points = []
    for i in range(10):
        r = size if i % 2 == 0 else size / 2.2
        angle = i * math.pi / 5 - math.pi / 2
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(points, fill=color)


def is_valid_drop_channel(channel: Optional[discord.abc.GuildChannel], allow_system: bool = False) -> bool:
    """Checks if a channel is appropriate for NBA card drops (not a welcome/rules/log channel, and must be public)."""
    if not channel or not isinstance(channel, discord.TextChannel):
        return False
    if not is_public_community_channel(channel):
        return False
    if not channel.permissions_for(channel.guild.me).send_messages:
        return False
    if not channel.permissions_for(channel.guild.me).attach_files:
        return False
    if not allow_system and channel.guild.system_channel and channel.id == channel.guild.system_channel.id:
        return False
    cname = channel.name.lower().replace("_", "-")
    for kw in IGNORED_DROP_CHANNEL_KEYWORDS:
        if kw in cname:
            return False
    return True


def get_best_drop_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """Finds the best chat channel for wild NBA card drops (prioritizing general/chat and excluding welcome/logs)."""
    # 1. Check last active chat channel if valid
    chan_id = _guild_last_active_channels.get(guild.id)
    if chan_id:
        cand = guild.get_channel(chan_id)
        if is_valid_drop_channel(cand):
            return cand

    # 2. Search for common active chat channels
    chat_keywords = ["chat", "general", "main", "lounge", "talk", "hangout", "nba", "cards", "bot-commands", "commands", "gaming"]
    valid_text_channels = [ch for ch in guild.text_channels if is_valid_drop_channel(ch)]
    
    for kw in chat_keywords:
        for ch in valid_text_channels:
            if kw in ch.name.lower():
                return ch

    # 3. Fallback to any valid text channel that isn't welcome/logs
    if valid_text_channels:
        return valid_text_channels[0]

    return None


def get_gm_rank(wins: int) -> Dict[str, Any]:
    """Calculates GM rank title, tier icon, visual progress bar and wins needed for promotion."""
    for rank in GM_RANKS:
        if rank["min_wins"] <= wins <= rank["max_wins"]:
            if rank["next_wins"] > rank["min_wins"]:
                span = rank["next_wins"] - rank["min_wins"]
                progress = min(span, max(0, wins - rank["min_wins"]))
                pct = int((progress / span) * 100)
                filled = int((progress / span) * 8)
                bar = "🟩" * filled + "⬜" * (8 - filled)
            else:
                pct = 100
                bar = "🟩" * 8
            return {
                "name": rank["name"],
                "icon": rank["icon"],
                "title": f"{rank['icon']} {rank['name']}",
                "next": rank["next"],
                "next_wins": rank["next_wins"],
                "needed": max(0, rank["next_wins"] - wins),
                "bar": bar,
                "pct": pct
            }
    return {"name": "Hall of Famer GM", "icon": "🏛️", "title": "🏛️ Hall of Famer GM", "next": "MAX", "next_wins": 50, "needed": 0, "bar": "🟩" * 8, "pct": 100}


def get_nba_card(identifier: str) -> Optional[Dict[str, Any]]:
    """Intelligently look up an NBA card by ID, nickname, player name, tier, OVR rating, or Holo Foil edition with 100% database fallback protection."""
    if not identifier:
        return None
    clean = str(identifier).strip().lower().replace("🌟", "").strip()
    is_holo = False
    if "(holo foil)" in clean or "(holo)" in clean or "(foil)" in clean:
        is_holo = True
        clean = clean.replace("(holo foil)", "").replace("(holo)", "").replace("(foil)", "").strip()
    if clean.startswith("holo_") or clean.startswith("holo-"):
        is_holo = True
        clean = clean[5:]
    elif clean.endswith("_holo") or clean.endswith("-holo"):
        is_holo = True
        clean = clean[:-5]
    base_identifier = clean

    # 1. Direct Catalog Match
    card = None
    for _c in NBA_2K_MOBILE_CARDS:
        if _c["id"].lower() == base_identifier:
            card = _c
            break
    if not card and base_identifier in NBA_CARDS_BY_ID:
        card = NBA_CARDS_BY_ID[base_identifier]
    if not card and base_identifier in NBA_LEGACY_CARD_MAPPINGS:
        card = NBA_CARDS_BY_ID.get(NBA_LEGACY_CARD_MAPPINGS[base_identifier])

    if not card:
        # 2. Extract potential tier filter from query (e.g. "curry exclusive", "jordan dm", "wemby ruby")
        detected_tier = None
        query_without_tier = base_identifier
        for tier_name, tier_keys in NBA_TIER_QUERY_ALIASES:
            for tk in tier_keys:
                pattern = r'\b' + re.escape(tk) + r'\b'
                if re.search(pattern, query_without_tier):
                    detected_tier = tier_name
                    query_without_tier = re.sub(pattern, '', query_without_tier).strip()
                    break
            if detected_tier:
                break

        # 3. Extract potential OVR rating from query (e.g. "lebron 99", "brunson 89")
        detected_ovr = None
        ovr_match = re.search(r'\b(7[5-9]|8[0-9]|9[0-9]|100)\b', query_without_tier)
        if ovr_match:
            detected_ovr = int(ovr_match.group(1))
            query_without_tier = re.sub(r'\b(7[5-9]|8[0-9]|9[0-9]|100)\b', '', query_without_tier).strip()

        # Clean punctuation for nickname and fuzzy matching
        q_norm = unicodedata.normalize('NFKD', query_without_tier).encode('ascii', 'ignore').decode('utf-8').lower().replace(".", "").replace("'", "").strip()
        target_player = NBA_PLAYER_NICKNAMES.get(q_norm) or NBA_PLAYER_NICKNAMES.get(query_without_tier)
        target_norm = unicodedata.normalize('NFKD', target_player).encode('ascii', 'ignore').decode('utf-8').lower().replace(".", "").replace("'", "").strip() if target_player else ""

        candidates: List[Dict[str, Any]] = []
        if target_norm:
            for c in NBA_2K_MOBILE_CARDS:
                c_norm = unicodedata.normalize('NFKD', c["name"]).encode('ascii', 'ignore').decode('utf-8').lower().replace(".", "").replace("'", "").strip()
                if c_norm == target_norm:
                    if detected_tier and c["tier"] != detected_tier:
                        continue
                    if detected_ovr and c["ovr"] != detected_ovr:
                        continue
                    candidates.append(c)
        else:
            q_words = [w for w in q_norm.split() if len(w) >= 2]
            for c in NBA_2K_MOBILE_CARDS:
                c_norm = unicodedata.normalize('NFKD', c["name"]).encode('ascii', 'ignore').decode('utf-8').lower().replace(".", "").replace("'", "").strip()
                c_id = c["id"].lower()
                c_words = c_norm.split()

                is_player_match = False
                if q_norm:
                    if q_norm == c_norm or q_norm in c_words:
                        is_player_match = True
                    elif q_words and all(any(cw.startswith(qw) for cw in c_words) for qw in q_words):
                        is_player_match = True
                    elif len(q_norm) >= 4 and (q_norm in c_norm or q_norm in c_id):
                        is_player_match = True
                elif not q_norm and detected_tier:
                    is_player_match = True

                if is_player_match:
                    if detected_tier and c["tier"] != detected_tier:
                        continue
                    if detected_ovr and c["ovr"] != detected_ovr:
                        continue
                    candidates.append(c)

        if candidates:
            tier_prio = {
                "exclusive": 7,
                "dark_matter": 6,
                "galaxy_opal": 5,
                "diamond": 4,
                "amethyst": 3,
                "ruby": 2,
                "gold": 1
            }
            candidates.sort(key=lambda x: (tier_prio.get(x.get("tier", "gold"), 0), x.get("ovr", 0)), reverse=True)
            card = candidates[0]
        else:
            # Universal Tier/Legacy Fallback so NO database card ever fails resolution
            if base_identifier.startswith("excl-"):
                card = NBA_CARDS_BY_ID.get("excl-jordan-99")
            elif base_identifier.startswith("dm-"):
                card = NBA_CARDS_BY_ID.get("dm-jordan-99")
            elif base_identifier.startswith("go-"):
                card = NBA_CARDS_BY_ID.get("go-curry-97") or NBA_CARDS_BY_ID.get("go-duncan-98")
            elif base_identifier.startswith("dia-"):
                card = NBA_CARDS_BY_ID.get("dia-morant-93") or NBA_CARDS_BY_ID.get("dia-bam-93")
            elif base_identifier.startswith("amy-"):
                card = NBA_CARDS_BY_ID.get("dia-morant-93")
            elif base_identifier.startswith("ruby-"):
                card = NBA_CARDS_BY_ID.get("ruby-reaves-84") or NBA_CARDS_BY_ID.get("ruby-wemby-88")
            elif base_identifier.startswith("gold-"):
                card = NBA_CARDS_BY_ID.get("gold-caruso-81") or NBA_CARDS_BY_ID.get("gold-reaves-82")
            else:
                card = None

    if card and is_holo:
        holo_card = dict(card)
        holo_card["id"] = f"holo_{card['id']}"
        holo_card["name"] = f"🌟 {card['name']} (Holo Foil)"
        holo_card["ovr"] = min(100, card.get("ovr", 80) + 5)
        holo_card["is_holo"] = True
        holo_card["quicksell_vc"] = int(card.get("quicksell_vc", 100) * 1.50)
        
        # Boost nested 6-stat dictionary
        if "stats" in card and isinstance(card["stats"], dict):
            holo_stats = dict(card["stats"])
            for sk, sv in holo_stats.items():
                if isinstance(sv, (int, float)):
                    holo_stats[sk] = min(99, int(sv) + 5)
            holo_card["stats"] = holo_stats
            
        for stat in ["pts_inside", "pts_mid", "pts_3", "defense", "playmaking", "inside", "3pt", "def", "ply", "ath", "clu"]:
            if stat in holo_card and isinstance(holo_card[stat], (int, float)):
                holo_card[stat] = min(99, int(holo_card[stat]) + 5)
        return holo_card

    return card


def find_nba_player(pos: str, name: str) -> Optional[Dict[str, Any]]:
    clean_query = str(name).strip()
    norm_query = unicodedata.normalize('NFKD', clean_query).encode('ascii', 'ignore').decode('utf-8').lower()
    
    # 1. Search in 2K Mobile cards catalog via get_nba_card (supports Holo Foil, nicknames & IDs)
    c_obj = get_nba_card(clean_query)
    if c_obj:
        return card_to_player_dict(c_obj)

    # 2. Search in legacy NBA_DREAM_PLAYERS
    for p in NBA_DREAM_PLAYERS.get(pos, []):
        p_norm = unicodedata.normalize('NFKD', p["name"]).encode('ascii', 'ignore').decode('utf-8').lower()
        if p["name"].lower() == clean_query.lower() or p_norm == norm_query:
            return p
            
    # Search across all positions in NBA_DREAM_PLAYERS
    for p_list in NBA_DREAM_PLAYERS.values():
        for p in p_list:
            p_norm = unicodedata.normalize('NFKD', p["name"]).encode('ascii', 'ignore').decode('utf-8').lower()
            if p["name"].lower() == clean_query.lower() or p_norm == norm_query:
                return p
    return None


def get_nba_player_headshot(player_name: str) -> Optional[Image.Image]:
    """Fetches and caches high-resolution transparent NBA player headshot from local assets or official NBA CDN."""
    clean_name = player_name.strip()
    if clean_name in _NBA_HEADSHOT_CACHE:
        return _NBA_HEADSHOT_CACHE[clean_name]

    # 1. Check local assets/players directory first (for custom uploads like Carter Bryant)
    local_slug = clean_name.lower().replace(" ", "_").replace("'", "").replace(".", "")
    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        local_p = os.path.join(os.path.dirname(__file__), "assets", "players", f"{local_slug}{ext}")
        if os.path.exists(local_p):
            try:
                img = Image.open(local_p).convert("RGBA")
                _NBA_HEADSHOT_CACHE[clean_name] = img
                return img
            except Exception:
                pass

    pid = NBA_PLAYER_IMG_IDS.get(clean_name)
    if not pid:
        norm_input = unicodedata.normalize('NFKD', clean_name).encode('ascii', 'ignore').decode('utf-8').lower()
        for k, v in NBA_PLAYER_IMG_IDS.items():
            norm_k = unicodedata.normalize('NFKD', k).encode('ascii', 'ignore').decode('utf-8').lower()
            if norm_k == norm_input or norm_k in norm_input or norm_input in norm_k:
                pid = v
                break

    if not pid:
        return None

    import urllib.request
    urls = [
        f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png",
        f"https://cdn.nba.com/headshots/nba/latest/260x190/{pid}.png"
    ]
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = resp.read()
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                _NBA_HEADSHOT_CACHE[clean_name] = img
                return img
        except Exception:
            continue
            
    return None


def get_nba_player_moment_photo(player_name: str, card: Optional[Dict[str, Any]] = None) -> Optional[Image.Image]:
    """Fetches and caches high-resolution action photo for a player / card moment."""
    clean_name = str(player_name or "").strip()
    if not clean_name:
        return None
    cid = card.get("id", "").lower() if card else ""
    cache_key = f"{clean_name}_{cid}" if cid else clean_name
    if cache_key in _NBA_MOMENT_PHOTO_CACHE:
        return _NBA_MOMENT_PHOTO_CACHE[cache_key]

    # 1. Check local assets/moments/{player_name}/ directory
    folder_name = re.sub(r'[\\/*?:"<>|]', '', clean_name).strip()
    local_dir = os.path.join(os.path.dirname(__file__), "assets", "moments", folder_name)
    if os.path.exists(local_dir):
        for fname in ["1.jpg", "1.png", "2.jpg", "2.png"]:
            fpath = os.path.join(local_dir, fname)
            if os.path.exists(fpath):
                try:
                    img = Image.open(fpath).convert("RGBA")
                    _NBA_MOMENT_PHOTO_CACHE[cache_key] = img
                    return img
                except Exception:
                    pass

    # 2. Check card image_url or NBA_PLAYER_MOMENT_ACTION_URLS
    img_url = None
    if card and card.get("image_url"):
        img_url = card["image_url"]
    
    if not img_url:
        action_urls = globals().get("NBA_PLAYER_MOMENT_ACTION_URLS", {})
        p_norm = unicodedata.normalize('NFKD', clean_name).encode('ascii', 'ignore').decode('utf-8').lower().replace(".", "").replace("'", "").strip()
        img_url = action_urls.get(p_norm) or action_urls.get(clean_name.lower())

    if img_url:
        import urllib.request
        req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = resp.read()
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                _NBA_MOMENT_PHOTO_CACHE[cache_key] = img
                return img
        except Exception:
            pass

    # 3. Fallback to headshot
    headshot = get_nba_player_headshot(clean_name)
    if headshot:
        _NBA_MOMENT_PHOTO_CACHE[cache_key] = headshot
        return headshot

    return None


def get_nba_card_moment(card: Dict[str, Any]) -> str:
    """Returns the iconic real-life NBA match moment for a given card.
    For Holo Foil cards, returns the player's pinnacle / championship moment."""
    is_holo = bool(card.get("is_holo") or str(card.get("id", "")).startswith("holo_"))
    cid = str(card.get("id", "")).lower().replace("holo_", "").replace("holo-", "")
    
    moment = None
    if is_holo:
        pname_clean = card.get("name", "").replace("🌟", "").replace("(Holo Foil)", "").strip()
        best_c = None
        for c in NBA_2K_MOBILE_CARDS:
            if c["name"].lower().strip() == pname_clean.lower():
                if best_c is None or c.get("ovr", 0) > best_c.get("ovr", 0):
                    best_c = c
        if best_c and best_c["id"].lower() in NBA_REAL_MOMENTS:
            moment = NBA_REAL_MOMENTS[best_c["id"].lower()]

    if not moment and cid in NBA_REAL_MOMENTS:
        moment = NBA_REAL_MOMENTS[cid]
        
    if not moment:
        moment = card.get("moment") or card.get("theme") or f"{card.get('name', 'NBA Star')} Masterpiece"
        
    return f"🌟 [HOLO PINNACLE] {moment}" if is_holo else moment


def extract_picks_from_row(row: Any) -> Dict[str, Dict[str, Any]]:
    """Extracts 5-man roster dictionary from a database row with robust fallbacks and duplicate player sanitization."""
    team_data_raw = row.get("team_data") if isinstance(row, dict) else row[9]
    picks = {}
    if team_data_raw:
        try:
            picks = json.loads(team_data_raw)
        except Exception:
            pass
    if not picks or len(picks) < 5:
        pg_name = row.get("pg") if isinstance(row, dict) else row[2]
        sg_name = row.get("sg") if isinstance(row, dict) else row[3]
        sf_name = row.get("sf") if isinstance(row, dict) else row[4]
        pf_name = row.get("pf") if isinstance(row, dict) else row[5]
        c_name = row.get("c") if isinstance(row, dict) else row[6]
        picks = {
            "PG": find_nba_player("PG", str(pg_name)) or NBA_DREAM_PLAYERS["PG"][0],
            "SG": find_nba_player("SG", str(sg_name)) or NBA_DREAM_PLAYERS["SG"][0],
            "SF": find_nba_player("SF", str(sf_name)) or NBA_DREAM_PLAYERS["SF"][0],
            "PF": find_nba_player("PF", str(pf_name)) or NBA_DREAM_PLAYERS["PF"][0],
            "C": find_nba_player("C", str(c_name)) or NBA_DREAM_PLAYERS["C"][0],
        }

    # Deduplication and unique player sanitization across all 5 positions
    seen_names: Set[str] = set()
    for pos in ["PG", "SG", "SF", "PF", "C"]:
        p = picks.get(pos)
        pname = p.get("name", "").strip().lower() if isinstance(p, dict) else ""
        if not p or not pname or pname in seen_names:
            # Duplicate or invalid found! Replace with valid unique fallback player for this position
            for cand in NBA_DREAM_PLAYERS.get(pos, []):
                cand_name = cand.get("name", "").strip().lower()
                if cand_name not in seen_names:
                    picks[pos] = cand
                    pname = cand_name
                    break
        if pname:
            seen_names.add(pname)

    return picks


def evaluate_dream_team(picks: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    players = list(picks.values())
    total_cost = sum(p.get("cost", 1) for p in players)
    
    avg_3pt = sum(p.get("pts_3", 80) for p in players) / 5.0
    avg_def = sum(p.get("defense", 80) for p in players) / 5.0
    avg_ply = sum(p.get("playmaking", 80) for p in players) / 5.0
    avg_ins = sum(p.get("inside", 80) for p in players) / 5.0
    avg_clu = sum(p.get("clutch", 80) for p in players) / 5.0

    synergy_bonuses = 0.0
    strengths = []
    weaknesses = []

    shooters = [p for p in players if p.get("pts_3", 80) >= 88]
    if len(shooters) >= 3:
        synergy_bonuses += 2.5
        strengths.append("🎯 **Elite 5-Out Floor Spacing** (+2.5 OVR)")
    elif avg_3pt < 80:
        weaknesses.append("⚠️ **Clogged Paint**: Low outside shooting limits penetration.")

    defenders = [p for p in players if p.get("defense", 80) >= 94]
    if len(defenders) >= 3:
        synergy_bonuses += 2.5
        strengths.append("🔒 **Lockdown Defensive Anchor** (+2.5 OVR)")
    elif avg_def < 84:
        weaknesses.append("⚠️ **Defensive Holes**: Perimeter guards can get targeted.")

    elite_passers = [p for p in players if p.get("playmaking", 80) >= 95]
    if elite_passers:
        synergy_bonuses += 2.0
        strengths.append("🧠 **Showtime Floor Vision** (+2.0 OVR)")
    elif avg_ply < 82:
        weaknesses.append("⚠️ **Iso-Heavy**: Lacks a pure pass-first floor general.")

    if picks.get("C", {}).get("inside", 0) >= 98 or picks.get("PF", {}).get("inside", 0) >= 98:
        synergy_bonuses += 1.5
        strengths.append("💥 **Unstoppable Rim Pressure** (+1.5 OVR)")

    dm_count = sum(1 for p in players if p.get("tier") == "dark_matter" or p.get("ovr", 0) >= 99)
    go_count = sum(1 for p in players if p.get("tier") == "galaxy_opal" or p.get("ovr", 0) in [97, 98])
    if dm_count >= 3:
        synergy_bonuses += 2.0
        strengths.append(f"🌌 **Dark Matter Dynasty** ({dm_count}x GOAT Cards, +2.0 OVR)")
    elif dm_count + go_count >= 4:
        synergy_bonuses += 1.5
        strengths.append(f"💎 **All-Star Synergy** ({dm_count + go_count}x Elite Cards, +1.5 OVR)")
    else:
        synergy_bonuses += 1.0
        strengths.append("⚡ **Balanced Starting 5 Chemistry** (+1.0 OVR)")

    if not strengths:
        strengths.append("⚡ **Solid Fundamental All-Around Play**")
    if not weaknesses:
        weaknesses.append("✨ **Flawless Roster Construction (No Obvious Weaknesses!)**")

    card_ovrs = [p.get("ovr") for p in players if p.get("ovr") is not None]
    if len(card_ovrs) == 5:
        avg_card_ovr = sum(card_ovrs) / 5.0
        base_ovr = (avg_3pt * 0.15) + (avg_def * 0.15) + (avg_ply * 0.15) + (avg_ins * 0.15) + (avg_clu * 0.10) + (avg_card_ovr * 0.30)
    else:
        base_ovr = (avg_3pt * 0.22) + (avg_def * 0.25) + (avg_ply * 0.20) + (avg_ins * 0.20) + (avg_clu * 0.13)

    final_ovr = min(99.9, round(base_ovr + synergy_bonuses, 1))

    if final_ovr >= 97.0:
        tier_label = "🏆 S+ Tier • Dynasty Champion"
        tier_color = discord.Color.gold()
    elif final_ovr >= 94.0:
        tier_label = "🌟 S Tier • Finals Favorite"
        tier_color = discord.Color.from_rgb(255, 215, 0)
    elif final_ovr >= 90.0:
        tier_label = "💎 A Tier • Deep Contender"
        tier_color = discord.Color.blue()
    else:
        tier_label = "⚡ B Tier • Playoff Squad"
        tier_color = discord.Color.teal()

    return {
        "total_cost": total_cost,
        "ovr": final_ovr,
        "tier": tier_label,
        "color": tier_color,
        "avg_3pt": round(avg_3pt, 1),
        "avg_def": round(avg_def, 1),
        "avg_ply": round(avg_ply, 1),
        "avg_ins": round(avg_ins, 1),
        "avg_clu": round(avg_clu, 1),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "picks": picks
    }


def generate_dream_team_card(
    user_name: str,
    picks: Dict[str, Dict[str, Any]],
    evaluation: Dict[str, Any],
    stats: Optional[Dict[str, Any]] = None
) -> io.BytesIO:
    """Generates a high-definition 1600x960 NBA 2K MyTEAM lineup graphic showcasing the 5 starting player photo headshots, ratings, tier badge, and team telemetry."""
    W, H = 1600, 960
    # Create base dark stadium canvas
    canvas = Image.new("RGBA", (W, H), (8, 12, 22, 255))
    draw = ImageDraw.Draw(canvas)

    # 1. Realistic Stadium & Court Background
    for y in range(H):
        t = y / H
        r = int(7 * (1 - t) + 14 * t)
        g = int(10 * (1 - t) + 20 * t)
        b = int(18 * (1 - t) + 38 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # Subtle hardwood angled floor grid in lower half
    floor_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fl_draw = ImageDraw.Draw(floor_layer)
    for x_line in range(-200, W + 400, 70):
        fl_draw.line([(x_line, H - 280), (x_line - 160, H)], fill=(255, 255, 255, 5), width=1)
        fl_draw.line([(x_line, H - 280), (x_line + 160, H)], fill=(255, 255, 255, 5), width=1)

    fl_draw.ellipse([W//2 - 450, H - 320, W//2 + 450, H + 320], outline=(59, 130, 246, 20), width=2)
    fl_draw.ellipse([W//2 - 140, H - 230, W//2 + 140, H + 100], outline=(255, 184, 0, 25), width=2)
    fl_draw.line([(W//2, H - 280), (W//2, H)], fill=(255, 255, 255, 15), width=2)

    canvas = Image.alpha_composite(canvas, floor_layer)
    draw = ImageDraw.Draw(canvas)

    # 2. Top Header HUD Banner
    draw.rounded_rectangle([(35, 20), (W - 35, 135)], radius=18, fill=(13, 18, 30, 245), outline=(38, 50, 72, 255), width=2)
    draw.line([(55, 20), (W - 55, 20)], fill=(255, 184, 0, 200), width=2)

    f_tag = _get_nba_card_font(12, bold=True)
    f_team_name = _get_nba_card_font(34, bold=True)
    f_meta = _get_nba_card_font(14, bold=False)

    draw.text((65, 32), "NBA 2K MYTEAM  |  STARTING 5 ROSTER", fill=(255, 184, 0, 255), font=f_tag)
    draw.text((65, 52), f"{user_name.upper()}'S SQUAD", fill=(255, 255, 255, 255), font=f_team_name)

    rec_text = "FRANCHISE ROSTER  •  ALL-TIME CHAMPIONSHIP LINEUP"
    if stats:
        w = stats.get("wins", 0)
        l = stats.get("losses", 0)
        st = stats.get("streak", 0)
        st_label = f"HOT STREAK: {st}W" if st > 0 else (f"COLD: {abs(st)}L" if st < 0 else "EVEN")
        rec_text = f"CAREER RECORD: {w}W - {l}L  •  {st_label}  •  BEST: {stats.get('best_streak', 0)}W"
    draw.text((65, 98), rec_text, fill=(148, 163, 184, 255), font=f_meta)

    # Right: OVR Badge & Tier Indicator
    ovr_val = evaluation.get("ovr", 90.0)
    tier_raw = evaluation.get("tier", "S Tier").split("•")[0].strip()
    total_cost = evaluation.get("total_cost", 15)

    ovr_box_w = 280
    ovr_box_x = W - 55 - ovr_box_w

    draw.rounded_rectangle([(ovr_box_x, 32), (W - 55, 85)], radius=12, fill=(8, 12, 22, 255), outline=(255, 184, 0, 255), width=2)
    _draw_star_polygon(draw, (ovr_box_x + 28, 58), 14, (255, 184, 0, 255))

    f_ovr_big = _get_nba_card_font(28, bold=True)
    f_tier_lbl = _get_nba_card_font(13, bold=True)
    draw.text((ovr_box_x + 50, 42), f"{ovr_val}", fill=(255, 255, 255, 255), font=f_ovr_big)
    draw.text((ovr_box_x + 130, 49), tier_raw.upper(), fill=(255, 184, 0, 255), font=f_tier_lbl)

    f_sal_txt = _get_nba_card_font(13, bold=True)
    draw.text((ovr_box_x, 98), f"STARTING 5 • {tier_raw.upper()}", fill=(203, 213, 225, 255), font=f_sal_txt)

    bar_sal_x = ovr_box_x + 130
    bar_sal_w = (W - 55) - bar_sal_x
    draw.rounded_rectangle([(bar_sal_x, 101), (W - 55, 113)], radius=4, fill=(24, 34, 52, 255))
    ovr_pct = min(1.0, max(0.0, (ovr_val - 70.0) / 30.0))
    bar_fill = int(ovr_pct * bar_sal_w)
    draw.rounded_rectangle([(bar_sal_x, 101), (bar_sal_x + bar_fill, 113)], radius=4, fill=(255, 184, 0, 255))

    # 3. 5 Large Realistic Player Cards (PG | SG | SF | PF | C)
    positions = ["PG", "SG", "SF", "PF", "C"]
    card_w = 280
    card_h = 630
    start_x = 50
    gap = 25
    y_card = 165

    tier_styling = {
        5: {
            "name": "DARK MATTER",
            "border": (255, 45, 85, 255),
            "accent": (255, 184, 0, 255),
            "bg_glow": (255, 45, 85, 55),
            "header_fill": (45, 15, 25, 255)
        },
        4: {
            "name": "GALAXY OPAL",
            "border": (168, 85, 247, 255),
            "accent": (232, 121, 249, 255),
            "bg_glow": (168, 85, 247, 50),
            "header_fill": (35, 18, 48, 255)
        },
        3: {
            "name": "DIAMOND",
            "border": (59, 130, 246, 255),
            "accent": (56, 189, 248, 255),
            "bg_glow": (59, 130, 246, 45),
            "header_fill": (15, 28, 48, 255)
        },
        2: {
            "name": "AMETHYST",
            "border": (34, 197, 94, 255),
            "accent": (74, 222, 128, 255),
            "bg_glow": (34, 197, 94, 45),
            "header_fill": (15, 38, 25, 255)
        },
        1: {
            "name": "RUBY / GOLD",
            "border": (148, 163, 184, 255),
            "accent": (226, 232, 240, 255),
            "bg_glow": (148, 163, 184, 40),
            "header_fill": (25, 32, 44, 255)
        }
    }

    f_pos = _get_nba_card_font(18, bold=True)
    f_cost = _get_nba_card_font(18, bold=True)
    f_ovr_tag = _get_nba_card_font(10, bold=True)
    f_p_ovr_num = _get_nba_card_font(34, bold=True)
    f_fn = _get_nba_card_font(12, bold=True)
    f_team_arch = _get_nba_card_font(12, bold=False)
    f_stat_name = _get_nba_card_font(13, bold=True)
    f_stat_num = _get_nba_card_font(14, bold=True)
    f_tier_ribbon = _get_nba_card_font(11, bold=True)

    for idx, pos in enumerate(positions):
        cx = start_x + idx * (card_w + gap)
        cy = y_card
        pl = picks.get(pos, {"name": "Empty", "cost": 1, "team": "NBA", "archetype": "Star", "pts_3": 80, "defense": 80, "inside": 80, "clutch": 80})
        cost = pl.get("cost", 1)
        tier_str = str(pl.get("tier", "")).lower()

        if pl.get("ovr"):
            p_ovr = int(pl["ovr"])
        else:
            p_stats_vals = [pl.get("pts_3", 80), pl.get("defense", 80), pl.get("inside", 80), pl.get("clutch", 80)]
            calc_ovr = int(sum(p_stats_vals) / len(p_stats_vals))
            if cost == 5: p_ovr = max(98, min(99, calc_ovr + 5))
            elif cost == 4: p_ovr = max(94, min(97, calc_ovr + 3))
            elif cost == 3: p_ovr = max(90, min(93, calc_ovr + 1))
            elif cost == 2: p_ovr = max(86, min(89, calc_ovr))
            else: p_ovr = max(80, min(85, calc_ovr))

        if tier_str == "dark_matter" or p_ovr >= 99:
            ts = tier_styling[5]
        elif tier_str == "galaxy_opal" or p_ovr >= 97:
            ts = tier_styling[4]
        elif tier_str == "diamond" or p_ovr >= 93:
            ts = tier_styling[3]
        elif tier_str == "amethyst" or p_ovr >= 89:
            ts = tier_styling[2]
        else:
            ts = tier_styling[1]

        b_col = ts["border"]
        a_col = ts["accent"]

        # 3.1 Card Outer Glow & Shadow
        card_fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cfx_draw = ImageDraw.Draw(card_fx)
        cfx_draw.rounded_rectangle([(cx - 10, cy - 10), (cx + card_w + 10, cy + card_h + 10)], radius=24, fill=ts["bg_glow"])
        canvas = Image.alpha_composite(canvas, card_fx)
        draw = ImageDraw.Draw(canvas)

        # 3.2 Card Body Background (Dark Matte Carbon Plate)
        draw.rounded_rectangle([(cx, cy), (cx + card_w, cy + card_h)], radius=18, fill=(12, 17, 28, 255), outline=b_col, width=3)
        draw.rounded_rectangle([(cx + 5, cy + 5), (cx + card_w - 5, cy + card_h - 5)], radius=14, outline=(255, 255, 255, 25), width=1)

        # 3.3 Card Top Header: Position Badge, Cost Badge, and OVR Number
        draw.rounded_rectangle([(cx + 12, cy + 12), (cx + 65, cy + 48)], radius=8, fill=(20, 28, 44, 255), outline=b_col, width=2)
        draw.text((cx + 23, cy + 19), pos, fill=(255, 255, 255, 255), font=f_pos)

        draw.rounded_rectangle([(cx + 74, cy + 12), (cx + 126, cy + 48)], radius=8, fill=(20, 28, 44, 255), outline=a_col, width=2)
        draw.text((cx + 84, cy + 19), f"${cost}", fill=a_col, font=f_cost)

        draw.text((cx + card_w - 68, cy + 12), "OVR", fill=(148, 163, 184, 255), font=f_ovr_tag)
        draw.text((cx + card_w - 68, cy + 20), str(p_ovr), fill=b_col, font=f_p_ovr_num)

        # 3.4 Backdrop aura glow behind player photo
        aura_img = Image.new("RGBA", (card_w, 280), (0, 0, 0, 0))
        aura_draw = ImageDraw.Draw(aura_img)
        aura_draw.ellipse([15, 20, card_w - 15, 270], fill=ts["bg_glow"])
        canvas.paste(aura_img, (cx, cy + 45), aura_img)
        draw = ImageDraw.Draw(canvas)

        # 3.5 Large Real Match Moment Artwork (Dominant Element!)
        p_name = pl.get("name", "Player")
        action_photo = get_nba_player_moment_photo(p_name)
        photo_rendered = False
        
        if action_photo:
            try:
                photo_w, photo_h = card_w - 16, 268
                px, py = cx + 8, cy + 54
                aspect = action_photo.width / max(1, action_photo.height)
                if aspect > (photo_w / photo_h):
                    scale_h = photo_h
                    scale_w = int(scale_h * aspect)
                else:
                    scale_w = photo_w
                    scale_h = int(scale_w / aspect)
                p_scaled = action_photo.resize((scale_w, scale_h), Image.Resampling.LANCZOS)
                left = max(0, (p_scaled.width - photo_w) // 2)
                top = max(0, (p_scaled.height - photo_h) // 3)
                p_cropped = p_scaled.crop((left, top, left + photo_w, top + photo_h))
                p_cropped = ImageEnhance.Contrast(p_cropped).enhance(1.15)
                p_cropped = ImageEnhance.Color(p_cropped).enhance(1.18)

                mask = Image.new("L", (photo_w, photo_h), 255)
                m_draw = ImageDraw.Draw(mask)
                for my in range(0, 30):
                    m_draw.line([(0, my), (photo_w, my)], fill=int(255 * (my / 30)))
                fade_bot = 60
                for my in range(photo_h - fade_bot, photo_h):
                    m_draw.line([(0, my), (photo_w, my)], fill=int(255 * (1.0 - (my - (photo_h - fade_bot)) / fade_bot)))
                for mx in range(0, 20):
                    for my in range(photo_h):
                        cur = mask.getpixel((mx, my))
                        mask.putpixel((mx, my), min(cur, int(255 * (mx / 20))))
                        mask.putpixel((photo_w - 1 - mx, my), min(cur, int(255 * (mx / 20))))
                mask = mask.filter(ImageFilter.GaussianBlur(5))

                p_rgba = p_cropped.convert("RGBA")
                p_rgba.putalpha(mask)

                photo_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                photo_layer.paste(p_rgba, (px, py))
                canvas = Image.alpha_composite(canvas, photo_layer)
                draw = ImageDraw.Draw(canvas)
                photo_rendered = True
            except Exception as hs_err:
                logger.debug(f"Error pasting moment photo for {p_name}: {hs_err}")

        if not photo_rendered:
            headshot = get_nba_player_headshot(p_name)
            if headshot:
                try:
                    target_w = card_w - 10
                    target_h = int(target_w * (headshot.height / headshot.width))
                    hs_res = headshot.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    
                    fade_mask = Image.new("L", hs_res.size, 255)
                    f_mask_draw = ImageDraw.Draw(fade_mask)
                    fade_start_y = int(target_h * 0.72)
                    for my in range(fade_start_y, target_h):
                        alpha_factor = int(255 * (1.0 - (my - fade_start_y) / (target_h - fade_start_y)))
                        f_mask_draw.line([(0, my), (target_w, my)], fill=alpha_factor)
                    
                    hs_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    r_c, g_c, b_c, a_c = hs_res.split()
                    merged_alpha = Image.composite(a_c, Image.new("L", a_c.size, 0), fade_mask)
                    hs_res.putalpha(merged_alpha)

                    hs_layer.paste(hs_res, (cx + 5, cy + 48))
                    canvas = Image.alpha_composite(canvas, hs_layer)
                    draw = ImageDraw.Draw(canvas)
                except Exception as hs_err:
                    logger.debug(f"Error pasting headshot for {p_name}: {hs_err}")
            else:
                ph = Image.new("RGBA", (card_w - 30, 260), (20, 28, 44, 200))
                ph_draw = ImageDraw.Draw(ph)
                f_ph = _get_nba_card_font(36, bold=True)
                initials = "".join([p[0] for p in p_name.split(" ") if p])[:2]
                ph_draw.text(((card_w - 30)//2 - 25, 90), initials, fill=b_col, font=f_ph)
                canvas.paste(ph, (cx + 15, cy + 55), ph)
                draw = ImageDraw.Draw(canvas)

        # 3.6 Player Nameplate Banner (Lower-middle)
        np_y = cy + 325
        draw.rounded_rectangle([(cx + 10, np_y), (cx + card_w - 10, np_y + 78)], radius=12, fill=(8, 12, 20, 250), outline=b_col, width=2)
        
        name_parts = p_name.split(" ")
        first_name = name_parts[0] if len(name_parts) > 1 else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else name_parts[0]

        f_ln_size = 21 if len(last_name) <= 10 else (17 if len(last_name) <= 14 else 15)
        f_ln_dyn = _get_nba_card_font(f_ln_size, bold=True)

        draw.text((cx + 18, np_y + 8), first_name.upper(), fill=(148, 163, 184, 255), font=f_fn)
        draw.text((cx + 18, np_y + 24), last_name.upper(), fill=(255, 255, 255, 255), font=f_ln_dyn)
        
        arch_display = pl.get('archetype', 'Star')[:18].upper()
        draw.text((cx + 18, np_y + 53), f"{pl.get('team', 'NBA')}  •  {arch_display}", fill=a_col, font=f_team_arch)

        # 3.7 Player Attribute Stat Progress Bars (Bottom card container)
        stat_box_y = np_y + 88
        draw.rounded_rectangle([(cx + 10, stat_box_y), (cx + card_w - 10, cy + card_h - 32)], radius=10, fill=(6, 9, 16, 240), outline=(30, 41, 59, 255), width=1)
        
        stats_data = [
            ("3PT", pl.get("pts_3", 80), (56, 189, 248, 255)),   # Cyan 3pt
            ("DEF", pl.get("defense", 80), (74, 222, 128, 255)), # Green defense
            ("INS", pl.get("inside", 80), (248, 113, 113, 255)), # Red inside
            ("CLU", pl.get("clutch", 80), (251, 191, 36, 255))   # Gold clutch
        ]

        sy = stat_box_y + 9
        for s_tag, s_score, s_color in stats_data:
            draw.text((cx + 20, sy), s_tag, fill=(148, 163, 184, 255), font=f_stat_name)
            draw.text((cx + 58, sy), str(s_score), fill=(255, 255, 255, 255), font=f_stat_num)

            bx1 = cx + 92
            bx2 = cx + card_w - 22
            bw = bx2 - bx1
            draw.rounded_rectangle([(bx1, sy + 3), (bx2, sy + 11)], radius=4, fill=(20, 28, 44, 255))

            pct = max(0.10, min(1.0, (s_score - 55) / 44.0))
            fw = int(pct * bw)
            draw.rounded_rectangle([(bx1, sy + 3), (bx1 + fw, sy + 11)], radius=4, fill=s_color)

            sy += 23

        # 3.8 Card Tier Badge Ribbon at very bottom of card
        draw.rounded_rectangle([(cx + 25, cy + card_h - 26), (cx + card_w - 25, cy + card_h - 6)], radius=6, fill=(15, 22, 36, 255), outline=b_col, width=1)
        draw.text((cx + 40, cy + card_h - 23), ts["name"], fill=a_col, font=f_tier_ribbon)

    # 4. Bottom Team Telemetry HUD Strip
    hud_y = y_card + card_h + 18
    draw.rounded_rectangle([(35, hud_y), (W - 35, hud_y + 64)], radius=14, fill=(13, 18, 30, 245), outline=(38, 50, 72, 255), width=2)
    draw.line([(55, hud_y), (W - 55, hud_y)], fill=(59, 130, 246, 180), width=2)

    f_hud_lbl = _get_nba_card_font(13, bold=True)
    f_hud_val = _get_nba_card_font(15, bold=True)
    
    hud_metrics = [
        ("3PT SPACING", f"{evaluation.get('avg_3pt', 85)}", (56, 189, 248, 255)),
        ("DEFENSE CLAMP", f"{evaluation.get('avg_def', 85)}", (74, 222, 128, 255)),
        ("PLAYMAKING IQ", f"{evaluation.get('avg_ply', 85)}", (192, 132, 252, 255)),
        ("INSIDE FINISHING", f"{evaluation.get('avg_ins', 85)}", (248, 113, 113, 255)),
        ("CLUTCH GENE", f"{evaluation.get('avg_clu', 85)}", (251, 191, 36, 255))
    ]

    metric_w = (W - 100) // len(hud_metrics)
    for m_idx, (m_title, m_val, m_c) in enumerate(hud_metrics):
        mx = 60 + m_idx * metric_w
        draw.text((mx, hud_y + 14), m_title, fill=(148, 163, 184, 255), font=f_hud_lbl)
        draw.text((mx, hud_y + 34), m_val, fill=m_c, font=f_hud_val)
        if m_idx < len(hud_metrics) - 1:
            draw.line([(mx + metric_w - 20, hud_y + 15), (mx + metric_w - 20, hud_y + 50)], fill=(38, 50, 72, 255), width=1)

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG", quality=95)
    buf.seek(0)
    try:
        canvas.close()
    except Exception:
        pass
    clean_memory()
    return buf


def generate_nba_card_graphic(
    card: Dict[str, Any],
    is_mystery: bool = False,
    headshot_img: Optional[Image.Image] = None
) -> io.BytesIO:
    """Generates an authentic 520x760 NBA 2K Mobile-style card graphic with real-life NBA match moments,
    dynamic player aura lighting, feathered gradient composite, holographic foil lines, OVR shield, and HUD."""
    cache_key = f"{card.get('id', '')}_{is_mystery}_{card.get('is_holo', False)}_{card.get('ovr', 0)}"
    if not headshot_img and cache_key in _CARD_GRAPHIC_CACHE:
        buf = io.BytesIO(_CARD_GRAPHIC_CACHE[cache_key])
        buf.seek(0)
        return buf

    W, H = 520, 760
    tier_key = card.get("tier", "gold").lower()
    theme = NBA_2K_CARD_THEMES.get(tier_key, NBA_2K_CARD_THEMES["gold"])
    is_holo = bool(card.get("is_holo") or str(card.get("id", "")).startswith("holo_"))

    card_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    margin = 14
    rect_box = [(margin, margin), (W - margin, H - margin)]
    
    # 1. Base Gradient Canvas
    bg_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_layer)
    for y in range(margin, H - margin):
        t = (y - margin) / max(1, (H - 2 * margin))
        r = int(theme["bg_top"][0] * (1 - t) + theme["bg_bot"][0] * t)
        g = int(theme["bg_top"][1] * (1 - t) + theme["bg_bot"][1] * t)
        b = int(theme["bg_top"][2] * (1 - t) + theme["bg_bot"][2] * t)
        bg_draw.line([(margin, y), (W - margin, y)], fill=(r, g, b, 255))
        
    mask = Image.new("L", (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(rect_box, radius=24, fill=255)
    card_img.paste(bg_layer, (0, 0), mask)

    # 2. Cosmic / Holographic geometric laser lines & stadium flare
    grid_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(grid_layer)
    for i in range(-200, W + 300, 36):
        g_draw.line([(i, margin), (i + 180, H - margin)], fill=(*theme["glow"], 22), width=1)
        g_draw.line([(i + 180, margin), (i, H - margin)], fill=(*theme["glow"], 22), width=1)
    
    if is_holo:
        # Radiant rainbow holographic foil shimmer lines across card
        rainbow_colors = [(255, 100, 100), (255, 200, 50), (100, 255, 150), (50, 220, 255), (200, 100, 255)]
        for idx, i in enumerate(range(-100, W + 200, 28)):
            c = rainbow_colors[idx % len(rainbow_colors)]
            g_draw.line([(i, margin), (i + 220, H - margin)], fill=(*c, 45), width=2)
    
    # Concentric orbital stadium glow circles
    g_draw.ellipse([W//2 - 180, H//2 - 200, W//2 + 180, H//2 + 160], outline=(*theme["primary"], 55), width=2)
    g_draw.ellipse([W//2 - 130, H//2 - 150, W//2 + 130, H//2 + 110], outline=(*theme["glow"], 85), width=2)
    card_img = Image.alpha_composite(card_img, grid_layer)
    draw = ImageDraw.Draw(card_img)

    # 3. Player Artwork / Real Match Moment Composite
    if is_mystery:
        sil_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(sil_layer)
        cx, cy = W // 2, H // 2 - 25
        s_draw.ellipse([cx - 110, cy - 110, cx + 110, cy + 110], fill=(12, 16, 28, 230), outline=(*theme["glow"], 180), width=3)
        s_draw.ellipse([cx - 125, cy - 125, cx + 125, cy + 125], outline=(*theme["primary"], 90), width=2)
        
        f_q = _get_nba_card_font(120, bold=True)
        s_draw.text((cx - 36, cy - 75), "?", fill=theme["border"], font=f_q)
        
        s_draw.rounded_rectangle([(cx - 160, cy + 85), (cx + 160, cy + 125)], radius=10, fill=(10, 14, 24, 240), outline=(*theme["primary"], 200), width=2)
        f_who = _get_nba_card_font(16, bold=True)
        s_draw.text((cx - 115, cy + 96), "WHO'S THAT 2K STAR?", fill=(255, 255, 255, 255), font=f_who)
        card_img = Image.alpha_composite(card_img, sil_layer)
        draw = ImageDraw.Draw(card_img)
    else:
        # 1. Try loading real match moment photo from local catalog
        action_photo = None
        if not headshot_img:
            action_photo = get_nba_player_moment_photo(card.get("name", ""), card=card)

        if not action_photo:
            if not headshot_img:
                headshot_img = get_nba_player_headshot(card.get("name", ""))
            if not headshot_img:
                # Load tier-specific hardcoded iconic Wikipedia match moment
                action_photo = get_tier_default_moment_image(tier_key)

        if action_photo:
            try:
                target_w, target_h = 480, 420
                aspect = action_photo.width / max(1, action_photo.height)
                if aspect > 1.15:
                    scale_h = target_h
                    scale_w = int(scale_h * aspect)
                else:
                    scale_w = target_w
                    scale_h = int(scale_w / aspect)
                p_scaled = action_photo.resize((scale_w, scale_h), Image.Resampling.LANCZOS)
                left = max(0, (p_scaled.width - target_w) // 2)
                top = max(0, (p_scaled.height - target_h) // 3)
                p_cropped = p_scaled.crop((left, top, left + target_w, top + target_h))
                
                p_cropped = ImageEnhance.Contrast(p_cropped).enhance(1.18)
                p_cropped = ImageEnhance.Color(p_cropped).enhance(1.22)
                
                # 4-way feathered vignette & bottom fade
                mask = Image.new("L", (target_w, target_h), 255)
                m_draw = ImageDraw.Draw(mask)
                for y in range(0, 45):
                    alpha = int(255 * (y / 45))
                    m_draw.line([(0, y), (target_w, y)], fill=alpha)
                fade_bot = 120
                for y in range(target_h - fade_bot, target_h):
                    alpha = int(255 * (1.0 - (y - (target_h - fade_bot)) / fade_bot))
                    m_draw.line([(0, y), (target_w, y)], fill=alpha)
                for x in range(0, 30):
                    alpha = int(255 * (x / 30))
                    for y in range(target_h):
                        cur = mask.getpixel((x, y))
                        mask.putpixel((x, y), min(cur, alpha))
                        mask.putpixel((target_w - 1 - x, y), min(cur, alpha))
                mask = mask.filter(ImageFilter.GaussianBlur(8))
                
                px = (W - target_w) // 2
                py = 70
                p_rgba = p_cropped.convert("RGBA")
                p_rgba.putalpha(mask)
                photo_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                photo_layer.paste(p_rgba, (px, py))
                card_img = Image.alpha_composite(card_img, photo_layer)
                draw = ImageDraw.Draw(card_img)
            except Exception:
                action_photo = None

        if not action_photo and headshot_img:
            try:
                # Enhance vibrancy & contrast for intense live match lighting
                enh_con = ImageEnhance.Contrast(headshot_img)
                p_enhanced = enh_con.enhance(1.18)
                enh_col = ImageEnhance.Color(p_enhanced)
                p_enhanced = enh_col.enhance(1.22)

                # Scale player to bold full card presence
                target_w = 460
                aspect = p_enhanced.height / max(1, p_enhanced.width)
                target_h = int(target_w * aspect)
                p_scaled = p_enhanced.resize((target_w, target_h), Image.Resampling.LANCZOS)

                # Tier Energy Aura Backlight behind player silhouette
                aura_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                a_draw = ImageDraw.Draw(aura_layer)
                cx, cy = W // 2, 280
                a_draw.ellipse([cx - 175, cy - 185, cx + 175, cy + 185], fill=(*theme["glow"], 50))
                a_draw.ellipse([cx - 130, cy - 140, cx + 130, cy + 140], fill=(*theme["primary"], 75))
                aura_layer = aura_layer.filter(ImageFilter.GaussianBlur(30))
                card_img = Image.alpha_composite(card_img, aura_layer)

                px = (W - p_scaled.width) // 2
                py = 85

                # Feathered bottom alpha mask: smooth fade into the stats dock
                p_rgba = p_scaled.convert("RGBA")
                p_mask = p_rgba.split()[3]
                
                fade_h = 110
                grad_fade = Image.new("L", (p_scaled.width, p_scaled.height), 255)
                gf_draw = ImageDraw.Draw(grad_fade)
                for gy in range(p_scaled.height - fade_h, p_scaled.height):
                    alpha_val = int(255 * (1.0 - (gy - (p_scaled.height - fade_h)) / fade_h))
                    gf_draw.line([(0, gy), (p_scaled.width, gy)], fill=alpha_val)
                
                final_mask = Image.composite(grad_fade, Image.new("L", p_mask.size, 0), p_mask)
                card_img.paste(p_rgba, (px, py), final_mask)
                draw = ImageDraw.Draw(card_img)
            except Exception:
                pass

    # 4. Top Ribbon Bar: Tier Edition
    draw.rounded_rectangle([(margin + 12, margin + 10), (W - margin - 12, margin + 40)], radius=8, fill=(10, 14, 24, 230), outline=(*theme["border"], 180), width=1)
    
    tier_title = f"🌟 FORGED HOLO FOIL • {card['ovr']} OVR PINNACLE" if is_holo else f"{theme['name'].upper()} EDITION"
    f_tier = _get_nba_card_font(11 if is_holo else 13, bold=True)
    t_w = len(tier_title) * 7
    draw.text((W // 2 - t_w // 2, margin + 16), tier_title, fill=(255, 220, 90, 255) if is_holo else theme["border"], font=f_tier)
    
    # Draw crisp gold stars on left and right of tier title
    _draw_star_polygon(draw, (W // 2 - t_w // 2 - 16, margin + 25), 6, (255, 215, 0, 255) if is_holo else (*theme["border"], 255))
    _draw_star_polygon(draw, (W // 2 + t_w // 2 + 16, margin + 25), 6, (255, 215, 0, 255) if is_holo else (*theme["border"], 255))

    # 5. Top-Left HUD: OVR & Position Shield
    ovr_box = [(margin + 12, margin + 48), (margin + 110, margin + 144)]
    draw.rounded_rectangle(ovr_box, radius=12, fill=(12, 16, 28, 245), outline=(255, 215, 0, 240) if is_holo else (*theme["glow"], 230), width=2)
    f_ovr = _get_nba_card_font(38, bold=True)
    draw.text((margin + 20, margin + 52), str(card["ovr"]), fill=(255, 215, 0, 255) if is_holo else (255, 255, 255, 255), font=f_ovr)
    f_ovr_lbl = _get_nba_card_font(11, bold=True)
    draw.text((margin + 74, margin + 63), "OVR", fill=(255, 215, 0, 255) if is_holo else theme["border"], font=f_ovr_lbl)
    
    draw.line([(margin + 20, margin + 104), (margin + 102, margin + 104)], fill=(*theme["primary"], 140), width=1)
    f_pos = _get_nba_card_font(18, bold=True)
    draw.text((margin + 36, margin + 112), card.get("pos", "SF"), fill=theme["glow"], font=f_pos)

    # 6. Top-Right HUD: Team Badge
    team_box = [(W - margin - 100, margin + 48), (W - margin - 12, margin + 112)]
    draw.rounded_rectangle(team_box, radius=12, fill=(12, 16, 28, 245), outline=(*theme["primary"], 180), width=2)
    f_team_lbl = _get_nba_card_font(10, bold=True)
    draw.text((W - margin - 82, margin + 54), "TEAM", fill=(148, 163, 184, 255), font=f_team_lbl)
    f_team = _get_nba_card_font(22, bold=True)
    draw.text((W - margin - 86, margin + 72), card.get("team", "NBA"), fill=(255, 255, 255, 255), font=f_team)

    # 7. Real-Life NBA Match Moment Banner
    if not is_mystery:
        moment_text = get_nba_card_moment(card)
        m_box = [(margin + 14, H - margin - 228), (W - margin - 14, H - margin - 198)]
        draw.rounded_rectangle(m_box, radius=8, fill=(12, 18, 32, 250), outline=(255, 215, 0, 230) if is_holo else (*theme["glow"], 220), width=1)
        
        # Left and right star accents
        _draw_star_polygon(draw, (margin + 26, H - margin - 213), 5, (255, 215, 0, 255) if is_holo else (*theme["glow"], 255))
        _draw_star_polygon(draw, (W - margin - 26, H - margin - 213), 5, (255, 215, 0, 255) if is_holo else (*theme["glow"], 255))
        
        full_moment_lbl = f"REAL NBA MOMENT: {moment_text.upper()}"
        font_sz = 10
        if len(full_moment_lbl) > 42:
            font_sz = 9
        if len(full_moment_lbl) > 50:
            font_sz = 8
        f_mom = _get_nba_card_font(font_sz, bold=True)
        draw.text((margin + 36, H - margin - 220 + (10 - font_sz)), full_moment_lbl, fill=(255, 225, 100, 255) if is_holo else theme["glow"], font=f_mom)

    # 8. Lower Card Info & Stats Deck
    lower_box = [(margin + 12, H - margin - 190), (W - margin - 12, H - margin - 14)]
    draw.rounded_rectangle(lower_box, radius=16, fill=(10, 14, 26, 250), outline=(255, 215, 0, 240) if is_holo else (*theme["border"], 220), width=2)
    
    name_display = "??? MYSTERY 2K STAR ???" if is_mystery else card["name"].upper()
    f_name = _get_nba_card_font(22 if is_mystery else 24, bold=True)
    draw.text((margin + 24, H - margin - 178), name_display, fill=(255, 215, 0, 255) if is_holo else (255, 255, 255, 255), font=f_name)
    
    sub_title = "Guess the player name in chat!" if is_mystery else f"{card.get('theme', 'Signature Series')} • {card.get('pos', 'SF')}/{card.get('sec_pos', 'SG')}"
    f_sub = _get_nba_card_font(12, bold=False)
    draw.text((margin + 24, H - margin - 148), sub_title, fill=(255, 225, 120, 255) if is_holo else theme["border"], font=f_sub)
    
    draw.line([(margin + 24, H - margin - 126), (W - margin - 24, H - margin - 126)], fill=(*theme["primary"], 120), width=1)
    
    stats_dict = card.get("stats", {"3pt": 90, "def": 90, "ath": 90, "clu": 90, "ins": 90, "ply": 90})
    stat_keys = [("3PT", stats_dict.get("3pt", 90)), ("DEF", stats_dict.get("def", 90)), 
                 ("ATH", stats_dict.get("ath", 90)), ("CLU", stats_dict.get("clu", 90))]
    
    stat_w = (W - 2 * margin - 60) // 4
    for idx, (s_lbl, s_val) in enumerate(stat_keys):
        sx = margin + 24 + idx * (stat_w + 8)
        sy = H - margin - 116
        draw.rounded_rectangle([(sx, sy), (sx + stat_w, sy + 44)], radius=8, fill=(18, 24, 40, 230), outline=(255, 215, 0, 180) if is_holo else (*theme["primary"], 120), width=1)
        
        f_slbl = _get_nba_card_font(10, bold=True)
        draw.text((sx + 8, sy + 6), s_lbl, fill=(255, 215, 0, 255) if is_holo else (148, 163, 184, 255), font=f_slbl)
        
        f_sval = _get_nba_card_font(16, bold=True)
        val_str = "??" if is_mystery else str(s_val)
        draw.text((sx + 8, sy + 22), val_str, fill=(255, 235, 130, 255) if is_holo else theme["glow"], font=f_sval)

    # Footer
    f_foot = _get_nba_card_font(9, bold=True)
    draw.text((margin + 24, H - margin - 38), "NBA 2K MOBILE • AUTHENTIC COLLECTIBLE", fill=(100, 116, 139, 255), font=f_foot)
    cid_str = f"CARD ID: {card.get('id', 'nba-2k')}"
    draw.text((W - margin - 24 - len(cid_str) * 6, H - margin - 38), cid_str, fill=(100, 116, 139, 255), font=f_foot)

    # 9. Outer Border Trim
    if is_holo:
        draw.rounded_rectangle(rect_box, radius=24, outline=(255, 215, 0, 255), width=4)
        holo_inner = [(margin + 4, margin + 4), (W - margin - 4, H - margin - 4)]
        draw.rounded_rectangle(holo_inner, radius=20, outline=(255, 230, 100, 230), width=2)
    else:
        draw.rounded_rectangle(rect_box, radius=24, outline=(*theme["border"], 255), width=3)
        inner_box = [(margin + 4, margin + 4), (W - margin - 4, H - margin - 4)]
        draw.rounded_rectangle(inner_box, radius=20, outline=(*theme["primary"], 120), width=1)

    buf = io.BytesIO()
    card_img.save(buf, format="PNG")
    buf.seek(0)
    try:
        card_img.close()
    except Exception:
        pass
    clean_memory()
    return buf


def card_to_player_dict(card: Dict[str, Any]) -> Dict[str, Any]:
    """Converts an NBA 2K Mobile Card dictionary into a Starting 5 lineup player dictionary."""
    stats = card.get("stats", {})
    tier = str(card.get("tier", "gold")).lower()
    ovr = card.get("ovr", 85)
    
    tier_cost_map = {
        "exclusive": 6,
        "dark_matter": 5,
        "galaxy_opal": 4,
        "diamond": 3,
        "amethyst": 2,
        "ruby": 1,
        "gold": 1
    }
    cost = tier_cost_map.get(tier, 1)
    
    tier_emoji_map = {
        "exclusive": "👑",
        "dark_matter": "🌌",
        "galaxy_opal": "💎",
        "diamond": "🔷",
        "amethyst": "🟣",
        "ruby": "🔴",
        "gold": "🟡"
    }
    emoji = tier_emoji_map.get(tier, "🏀")
    if card.get("is_holo"):
        emoji = "🌟"
    
    pts_3 = stats.get("3pt", 80)
    defense = stats.get("def", 80)
    playmaking = stats.get("ply", 80)
    inside = stats.get("ins", 80)
    athleticism = stats.get("ath", 80)
    clutch = stats.get("clu", 80)
    
    arch = card.get("theme", "2K Star")
    if card.get("pos"):
        arch = f"{card.get('pos')} • {card.get('theme', '2K Star')}"
        
    favored = ["iso"]
    blocked = []
    if pts_3 >= 88:
        favored.append("three")
    elif pts_3 <= 70:
        blocked.append("three")
        
    if inside >= 88:
        favored.append("drive")
    if defense >= 88:
        favored.append("defense")
    if playmaking >= 88:
        favored.append("pnr")
        
    return {
        "name": card.get("name", "Unknown Player"),
        "cost": cost,
        "team": card.get("team", "NBA"),
        "tag": f"[{ovr} OVR {tier.replace('_', ' ').title()}] {card.get('theme', '')}",
        "emoji": emoji,
        "archetype": arch,
        "pts_3": pts_3,
        "defense": defense,
        "playmaking": playmaking,
        "inside": inside,
        "pts_inside": inside,
        "pts_mid": int((pts_3 + inside) / 2),
        "athleticism": athleticism,
        "clutch": clutch,
        "tier": tier,
        "ovr": ovr,
        "pos": card.get("pos", "SF"),
        "sec_pos": card.get("sec_pos"),
        "image_url": card.get("image_url"),
        "card_id": card.get("id"),
        "favored": favored,
        "blocked": blocked
    }


async def ensure_sweety_ai_team(guild_id: Optional[int] = None, target_id: Optional[int] = None, bot_user_id: Optional[int] = None) -> Dict[str, Any]:
    """Ensures Sweety AI Bot has the official 99.9 OVR All-Dark Matter G.O.A.T. Dynasty Starting 5 lineup saved in database."""
    bot_id = target_id or bot_user_id or 719932313919684670
    is_bot = (bot_user_id and bot_id == bot_user_id) or bot_id == 719932313919684670 or (target_id is None)
    row = await db.get_dream_team(bot_id)
    if not row or (is_bot and row.get("ovr_rating", 0) < 99.8):
        picks = {
            "PG": find_nba_player("PG", "dm-curry-99") or NBA_DREAM_PLAYERS["PG"][0],
            "SG": find_nba_player("SG", "dm-jordan-99") or NBA_DREAM_PLAYERS["SG"][0],
            "SF": find_nba_player("SF", "dm-lebron-99") or NBA_DREAM_PLAYERS["SF"][0],
            "PF": find_nba_player("PF", "dm-kd-99") or NBA_DREAM_PLAYERS["PF"][1],
            "C": find_nba_player("C", "dm-shaq-99") or NBA_DREAM_PLAYERS["C"][0],
        }
        eval_ai = evaluate_dream_team(picks)
        now = time.time()
        await db.save_dream_team(
            user_id=bot_id,
            guild_id=guild_id,
            pg=picks["PG"]["name"],
            sg=picks["SG"]["name"],
            sf=picks["SF"]["name"],
            pf=picks["PF"]["name"],
            c=picks["C"]["name"],
            total_cost=25,
            ovr_rating=eval_ai["ovr"],
            team_data=json.dumps(picks),
            updated_at=now
        )
        row = await db.get_dream_team(bot_id)
    return row


def _build_odds_lines(pack_data: Dict[str, Any]) -> str:
    """Returns a formatted string of pull odds for a pack."""
    odds = pack_data.get("odds", {})
    tier_order = ["dark_matter", "galaxy_opal", "diamond", "amethyst", "ruby", "gold"]
    lines = []
    for tier_key in tier_order:
        if tier_key in odds:
            t_info = NBA_2K_TIERS.get(tier_key, {})
            emoji = t_info.get("emoji", "•")
            name = t_info.get("short_name", tier_key.replace("_", " ").title())
            ovr = t_info.get("ovr_range", "??")
            pct = odds[tier_key] * 100
            bar_filled = max(1, round(pct / 10))
            bar = "▰" * bar_filled + "▱" * (10 - bar_filled)
            lines.append(f"{emoji} **{name}** (`{ovr} OVR`) — `{bar}` **{pct:.0f}%**")
    return "\n".join(lines) if lines else "No odds data available."


def roll_pack_card(pack_id: str = "starter", user_id: Optional[int] = None) -> Dict[str, Any]:
    """Rolls an authentic card from NBA_2K_MOBILE_CARDS using transparent pack odds."""
    pack_data = NBA_PACK_TYPES.get(pack_id.lower().strip(), NBA_PACK_TYPES["starter"])
    odds = pack_data.get("odds", {"gold": 1.0})
    tiers = list(odds.keys())
    weights = list(odds.values())

    chosen_tier = random.choices(tiers, weights=weights, k=1)[0]
    matching = [
        c for c in NBA_2K_MOBILE_CARDS
        if c.get("tier") == chosen_tier and not c.get("is_exclusive") and not c.get("is_holo")
    ]
    if not matching:
        matching = [c for c in NBA_2K_MOBILE_CARDS if c.get("tier") == chosen_tier]
    if not matching:
        matching = NBA_2K_MOBILE_CARDS
    return random.choice(matching)


def build_openpack_embed(
    user: Union[discord.User, discord.Member],
    pack_data: Dict[str, Any],
    card: Dict[str, Any],
    new_vc: int,
    is_new: bool = True,
    copies: int = 1
) -> discord.Embed:
    """Builds an authentic 2K Mobile pack reveal embed with transparent drop rates."""
    tier_info = NBA_2K_TIERS.get(card["tier"], NBA_2K_TIERS["gold"])
    moment = get_nba_card_moment(card)
    status_str = "🌟 **NEW CARD ADDED TO BINDER!**" if is_new else f"🔄 **DUPLICATE COPY OBTAINED (Now x{copies})**"

    embed = discord.Embed(
        title=f"{tier_info['emoji']} 2K MOBILE PACK REVEAL • [{card['ovr']} OVR] {card['name'].upper()}!",
        description=(
            f"# {tier_info['emoji']} {tier_info['name'].upper()} PULL!\n"
            f"**{user.mention} opened a {pack_data['name']}!**\n\n"
            f"{status_str}\n\n"
            f"**Player:** `{card['name']}` • **Pos:** `{card['pos']}` • **Team:** `{card['team']}`\n"
            f"⚡ **Real NBA Moment:** *{moment}*\n"
            f"**Theme:** *{card['theme']}*\n"
            f"*{card.get('quote', '')}*"
        ),
        color=tier_info["color"]
    )

    stats = card.get("stats", {})
    embed.add_field(
        name="📊 Ratings Breakdown",
        value=(
            f"`🎯 3PT `: **{stats.get('3pt', 80)}** | `🔒 DEF `: **{stats.get('def', 80)}** | `🧠 PLY `: **{stats.get('ply', 80)}**\n"
            f"`💥 INS `: **{stats.get('ins', 80)}** | `⚡ CLU `: **{stats.get('clu', 80)}** | `🏃 ATH `: **{stats.get('ath', 80)}**"
        ),
        inline=False
    )

    badges = card.get("badges", [])
    if badges:
        embed.add_field(name="🏆 Badges", value=" • ".join(f"`{b}`" for b in badges[:4]), inline=False)

    embed.add_field(
        name="💰 Virtual Currency Wallet",
        value=f"• **Remaining Balance:** `💰 {new_vc:,} VC`\n• **Quick-Sell Value:** `💰 {tier_info['quick_sell']:,} VC`",
        inline=False
    )

    embed.add_field(
        name=f"🎲 {pack_data['name']} Pull Rates (Fully Transparent)",
        value=_build_odds_lines(pack_data),
        inline=False
    )

    embed.set_footer(text=f"NBA 2K Mobile Pack Opening • Card ID: {card['id']} • Odds always shown honestly")
    embed.timestamp = discord.utils.utcnow()
    return embed


def build_pack_shop_embed(vc_balance: int) -> discord.Embed:
    """Builds the full NBA 2K Mobile Card Shop embed with transparent per-pack drop rates."""
    embed = discord.Embed(
        title="📦 NBA 2K Mobile Card Packs Shop",
        description=(
            f"**Your VC Balance:** `💰 {vc_balance:,} VC`\n\n"
            f"Select a pack below to buy and rip open!\n"
            f"All pull rates are **100% transparent and honest** — no hidden odds.\n"
        ),
        color=discord.Color.gold()
    )

    for pack_id, pack_data in NBA_PACK_TYPES.items():
        cost = pack_data["cost"]
        name = pack_data["name"]
        desc = pack_data.get("description", "")
        can_afford = "✅" if vc_balance >= cost else "❌"
        odds_text = _build_odds_lines(pack_data)
        embed.add_field(
            name=f"{can_afford} {name} — `{cost:,} VC`",
            value=f"*{desc}*\n{odds_text}",
            inline=False
        )

    embed.set_footer(text="Pull rates shown are exact probabilities • Use !packodds to view anytime")
    embed.timestamp = discord.utils.utcnow()
    return embed


