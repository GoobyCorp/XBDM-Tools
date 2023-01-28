#!/usr/bin/env python3

import re
import asyncio
from zlib import crc32
from typing import Any
from shlex import shlex
from pathlib import Path
from enum import IntEnum
from calendar import timegm
from struct import pack, unpack
from argparse import ArgumentParser
from datetime import datetime, timedelta, tzinfo

# xbdm variables
XBDM_PORT = 730
XBDM_BUFF_SIZE = 1460
XBDM_DIR = "DEVICES"

# time variables
EPOCH_AS_FILETIME = 116444736000000000
HUNDREDS_OF_NANOSECONDS = 10000000
ZERO = timedelta(0)
HOUR = timedelta(hours=1)

# arguments
XBDM_HOST: str = ""
SHADOWBOOT_PATH: str = ""

# regex
CODE_EXP = re.compile(r"^(\d+)-")

UPD_FILES_TO_DELETE = [
	"\\Device\\Harddisk0\\Partition1\\$systemupdate\\su20076000_00000000",
	"\\Device\\Harddisk0\\Partition1\\recint.ini",
	"\\Device\\Harddisk0\\Partition1\\netsim.ini",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\xonline.ini",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\zune.ini",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\messenger.xml",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\mediasite.xzp",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\livepack.xex",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\CodeCoverageData.cov",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\AudioCoverageData.cov",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\GraphicsCoverageData.cov",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\CodecsCoverageData.cov",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\NomniCoverageData.cov",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\xamdCoverageData.cov",
	"\\Device\\Harddisk0\\Partition1\\xbdm.ini",
	"\\Device\\Harddisk0\\Partition1\\xbdm.dll",
	"\\Device\\Harddisk0\\Partition1\\default.exe",
	"\\Device\\Harddisk0\\Partition1\\default.xex",
	"\\Device\\FlashFs\\friends.xex",
	"\\Device\\FlashFs\\feedback.xex",
	"\\Device\\FlashFs\\voicemail.xex",
	"\\Device\\FlashFs\\marketplace.xex",
	"\\Device\\FlashFs\\quickchat.xex",
	"\\Device\\FlashFs\\xmsgr.xex",
	"\\saferec.bmp",
	"\\Device\\Harddisk0\\Partition1\\xboxromw2d.bin",
	"\\Device\\Harddisk0\\Partition1\\xboxromw2td.bin",
	"\\Device\\Harddisk0\\Partition1\\xboxromtw2d.bin",
	"\\Device\\FlashFs\\xenonsclatin.xtt",
	"\\Device\\FlashFs\\ximedic_chs.xex",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\epg.ini",
	"\\xapi.xex",
	"\\xapid.xex",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\spsapi.xex",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\spsreng.xex",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\spsrx.xex"
]

UPD_DIRS_TO_DELETE = [
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\LiveEnvironments\\TestNet",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\LiveEnvironments\\TestNetMain",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\LiveEnvironments\\TestNet(NULL_AES)",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\override",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\jp-jp",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\de-de",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\en-au",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\en-gb",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\en-us",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\es-es",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\es-mx",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\fr-ca",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\fr-fr",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\it-it",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech\\ja-jp",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\xspeech",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\Database",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\calibrate",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\fwupdate",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\natal",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\KinectAdventuresDownloader",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\samples\\simpleskeletontracking",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\samples\\simplespeechrecognition",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\samples\\menuusinghandles",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\samples\\avatarretargeting",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\samples\\depthmapparticlestream",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\samples\\filtering",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\samples\\PlayspaceFeedback",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speech",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechlab",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuivoicecollection",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\identity"
]

UPD_FILES_TO_UPLOAD = [
	"\\connectx.xex",
	"\\xbdm.xex",
	"\\xstudio.xex",
	"\\xam.xex",
	"\\bootanim.xex",
	"\\hud.xex",
	"\\signin.xex",
	"\\vk.xex",
	"\\updater.xex",
	"\\deviceselector.xex",
	"\\minimediaplayer.xex",
	"\\gamerprofile.xex",
	"\\createprofile.xex",
	"\\mfgbootlauncher.xex",
	"\\huduiskin.xex",
	"\\dash.xex",
	"\\nomni.xex",
	"\\nomnifwm.xex",
	"\\nomnifwk.xex",
	"\\ximecore.xex",
	"\\processdump.xex",
	"\\ximedic.xex",
	"\\xenonjklatin.xtt",
	"\\xenonclatin.xtt",
	"\\xenonsclatin.xtt",
	"\\SegoeXbox-Light.xtt",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\dmext\\xsim.xex",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\music1.wma",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\music2.wma",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\music3.wma",
	"\\Device\\Harddisk0\\Partition1\\media\\PixPreviewInvalidMode.raw",
	"\\xbupdate.xex",
	"\\rrbkgnd.bmp",
	"\\recovery.ttf",
	"\\dashboard.xbx",
	"\\xlaunch.fdf",
	"\\xshell.xex",
	"\\xlaunch.strings"
]

UPD_FILES_TO_UPLOAD_SAMPLES = [
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\Avatar\\AvatarEditor.xex",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\AudioConsole3.exe",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Fonts\\Arial_16.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Fonts\\Impact_24.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Help\\Help.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Resource.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Shaders\\ConsoleMinificationPS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Shaders\\ConsolePS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Shaders\\ConsoleVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Shaders\\SpriteVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Dolphin\\Dolphin.exe",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Dolphin\\Media\\Meshes\\Dolphin1.xbg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Dolphin\\Media\\Meshes\\Dolphin2.xbg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Dolphin\\Media\\Meshes\\Dolphin3.xbg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Dolphin\\Media\\Meshes\\SeaFloor.xbg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Dolphin\\Media\\Resource.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Dolphin\\Media\\Shaders\\DolphinTween.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Dolphin\\Media\\Shaders\\SeaFloor.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Dolphin\\Media\\Shaders\\ShadeCausticsPixel.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\LightShafts.exe",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Meshes\\hebe.xbg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Resource.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\BackdropAmbientOnlyPS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\BackdropAmbientOnlyVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\BackdropDepthVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\BackdropMainVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\BackdropNoiseShadowPS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\CompositeFilteredFogPS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\ObjectMainVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\ObjectNoiseShadowPS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\OverlayMainVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\ShadowBlurPS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\SpotlightFrustumFrontPS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\SpotlightFrustumFrontVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\SpotlightFrustumPS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\SpotlightFrustumVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\SpotlightWireFrustumVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\VolVizShellsMainVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\VolVizShellsNoiseShadowPS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Textures\\LightShafts_NoiseVolume.dds",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\UIAuditioning\\UIAuditioning.xex",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\UIAuditioning\\media\\UIAuditioning.xzp",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\UIAuditioning\\media\\xarialuni.ttf",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\SceneViewer2.exe",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Effects\\Deferred.fxobj",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Effects\\PassPerLight.fxobj",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Effects\\PostEffects.fxobj",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Effects\\SimpleShaders.fxobj",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Effects\\Ubershader_Final.fxobj",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Effects\\Ubershader_Library.fxobj",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Fonts\\SegoeUI_16_Outline.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Fonts\\SegoeUI_24.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Scenes\\city-final.pmem",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Scenes\\city-final.xatg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\SceneViewerXui.xzp",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\SettingsUI.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Textures\\city-final.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\commandline.txt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\SimpleSkeletonTracking.exe",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Effects\\SimpleShaders.fxobj",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Fonts\\Arial_16.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Help\\Help.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Database.xmplr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\NuiIdentity.bin.be",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\SimpleSpeechRecognition.xex",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Fonts\\Arial_16_Speech.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_de_at.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_de_at.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_de_ch.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_de_ch.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_de_de.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_de_de.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_en_au.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_en_au.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_en_gb.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_en_gb.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_en_us.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_en_us.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_es_es.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_es_es.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_es_mx.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_es_mx.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_fr_ca.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_fr_ca.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_fr_ch.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_fr_ch.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_fr_fr.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_fr_fr.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_it_it.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_it_it.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_ja_jp.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_ja_jp.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_pt_br.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\medieval_pt_br.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\phonetic_alphabet_en_us.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\phonetic_alphabet_en_us.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_en_gb.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_en_gb.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_en_us.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_en_us.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_es_mx.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_es_mx.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_fr_ca.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_fr_ca.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_ja_jp.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_ja_jp.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_pt_br.cfg",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Grammars\\yes_no_pt_br.grtxt",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp3079",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp2055",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp1031",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp3081",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp2057",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp1033",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp3082",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp2058",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp3084",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp4108",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp1036",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp1040",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp1041",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\nuisp1046",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\MenuUsingHandles.exe",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Resource.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Shaders\\DepthPreviewPS.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Shaders\\DepthPreviewSmoothingVS.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Sounds\\04_Cursor_Prox_Closer_longer_loop.wav",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Sounds\\07_Cursor_Hotspot_Enter.wav",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Sounds\\09_Cursor_Inside_short_loop.wav",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Sounds\\10_Cursor_Hotspot_Exit.wav",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Sounds\\11_Btn_Interactive_Select.wav",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Sounds\\11_Cursor_Direction_Select.wav",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Sounds\\12_Btn_Select.wav",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Sounds\\19_Btn_Interactive_Focus.wav",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Sounds\\ProximityBlip2.wav",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\PlayspaceFeedback.exe",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Resource.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\background_ps.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\background_vs.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_opaque_ps.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_shiny_opaque_ps.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_shiny_transparent_ps.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_shiny_vs.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_transparent_ps.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_vs.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\head_opaque_ps.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\head_opaque_vs.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\AvatarRetargeting.exe",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Resource.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\HeadPosition.xmplr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\NuiHeadOrientation.bin.be",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Filtering\\Filtering.exe",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Filtering\\Media\\Resource.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\DepthMapParticleStream.exe",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Resource.xpr",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Shaders\\EdgeDetect.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Shaders\\GaussBlur5x5.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Shaders\\GetSegmentationFromDepthTexture.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Shaders\\PointSprite.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Shaders\\PointSprite.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Shaders\\PositionDiffuseTexcoord.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Shaders\\RenderTrail.xpu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Shaders\\ScreenSpaceShader.xvu",
	"\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Shaders\\TextureModDiffuse.xpu",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\nuiview.xex",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\nuiview.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\nuiview.xzp",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\pointsprite.png",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\Database.xmplr",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\NuiIdentity.bin.be",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\identity\\BiometricSigninSetup.xex",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\identity\\Media\\Effects\\SimpleShaders.fxobj",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\identity\\Media\\Fonts\\Arial_16.xpr",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\identity\\Media\\Help\\Help.xpr",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\speechLab.xex",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp3079",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp2055",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp1031",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp3081",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp2057",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp1033",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp3082",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp2058",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp3084",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp4108",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp1036",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp1040",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp1041",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\nuisp1046",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\phonetic_alphabet_en_us.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_de_at.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_de_ch.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_de_de.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_en_au.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_en_gb.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_en_us.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_es_mx.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_es_es.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_fr_ca.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_fr_ch.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_fr_fr.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_it_it.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_ja_jp.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\medieval_pt_br.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\yes_no_en_gb.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\yes_no_en_us.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\yes_no_es_mx.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\yes_no_fr_ca.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\yes_no_ja_jp.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\cfg\\yes_no_pt_br.cfg",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\NuiVoiceCollection\\nuivoicecollection.xex",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\NuiVoiceCollection\\media\\appconfig.xml",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\NuiVoiceCollection\\media\\languages.xml",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\NuiVoiceCollection\\media\\setup.xml",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\NuiVoiceCollection\\media\\setup_lang.xml",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\NuiVoiceCollection\\media\\example-script.txt",
	"\\Device\\Harddisk0\\Partition1\\DEVKIT\\NuiVoiceCollection\\media\\silence.wav",
]

UPD_FILES_TO_UPLOAD_AUX_EXT = [
	"\\Device\\SystemExtLink\\system.manifest",
	"\\Device\\SystemAuxLink\\online\\system.online.manifest.4451",
	"\\Device\\SystemExtLink\\Content\\0000000000000000\\FFFE07DF\\00008000\\FFFE07DF00000002",
	"\\Device\\SystemExtLink\\Content\\0000000000000000\\FFFE07DF\\00008000\\FFFE07DF00000006",
	"\\Device\\SystemExtLink\\Content\\0000000000000000\\FFFE07DF\\00008000\\FFFE07DF00000008",
	"\\Device\\SystemExtLink\\Content\\0000000000000000\\FFFE07DF\\00008000\\FFFE07DF00000001",
	"\\Device\\SystemExtLink\\20445100\\AvatarEditor.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\luaext.xex",
	"\\Device\\SystemExtLink\\20445100\\nuihud.xex",
	"\\Device\\SystemExtLink\\20445100\\dash.xex",
	"\\Device\\SystemExtLink\\20445100\\dash.ExtraAVCodecs.xex",
	"\\Device\\SystemExtLink\\20445100\\dash.ExtraAVCodecs2.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.OnlineCommon.lex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.Search.lex",
	"\\Device\\SystemExtLink\\20445100\\Dash.Search.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.MP.Core.xex",
	"\\Device\\SystemExtLink\\20417F00\\Title.Zune.xex",
	"\\Device\\SystemExtLink\\2506FD00\\PlayReady.xex",
	"\\Device\\SystemExtLink\\20445100\\Xam.Community.xex",
	"\\Device\\SystemExtLink\\20445100\\Xam.WordRegister.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.MP.AccountMgmt.lex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.MP.ContentExplorer.lex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.MP.MicrosoftStore.lex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.MP.Purchase.lex",
	"\\Device\\SystemExtLink\\20445100\\dash.natalpregame.xex",
	"\\Device\\SystemExtLink\\20445100\\Dash.NetworkStorage.lex",
	"\\Device\\SystemExtLink\\20445100\\dash.ClosedCaptionDll.xex",
	"\\Device\\SystemExtLink\\20445100\\Guide.TFA.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.Social.lex",
	"\\Device\\SystemExtLink\\20445100\\dashnui.xex",
	"\\Device\\SystemExtLink\\20445100\\Guide.Fitness.xex",
	"\\Device\\SystemExtLink\\20445100\\Guide.CSVTrans.xex",
	"\\Device\\SystemExtLink\\20445100\\Guide.AccountRecovery.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.ChatAndMessenger.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.Friends.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.MP.Download.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.MP.NuiPurchase.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.MP.Payment.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.MP.PaymentInst.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.MP.Purchase.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.MP.Subscriptions.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.NetworkStorage.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.NuiCommunity.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.SocialPost.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.PlayerFeedback.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.Beacons.xex",
	"\\Device\\SystemExtLink\\20445100\\XimeDic.xex",
	"\\Device\\SystemExtLink\\20445100\\XimeDic_CHS.xex",
	"\\Device\\SystemExtLink\\20445100\\XimeDicCh.xex",
	"\\Device\\SystemExtLink\\20445100\\ximedicex.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.Voicemail.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.FamilyCenter.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.FamilyWizard.lex",
	"\\Device\\SystemExtLink\\32000100\\Xna_TitleLauncher.xex",
	"\\Device\\SystemExtLink\\20445100\\BiometricSetup.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\LiveSignup.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.MP.LiveSignup.lex",
	"\\Device\\SystemExtLink\\20445100\\natalsu.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.PrivacyUI.xex",
	"\\Device\\SystemExtLink\\20445100\\Dash.FieldCalibration.lex",
	"\\Device\\SystemExtLink\\20445100\\Dash.NuiTroubleshooter.lex",
	"\\Device\\SystemExtLink\\20445100\\Guide.NuiTroubleshooter.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Title.NewLiveSignup.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.MP.LiveAccount.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Dash.LF.GamerTagChange.lex",
	"\\Device\\SystemExtLink\\20445100\\Dash.Kiosk.lex",
	"\\Device\\SystemExtLink\\20445100\\Guide.AvatarMiniCreator.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\Guide.Survey.xex",
	"\\Device\\SystemAuxLink\\online\\20445100\\TakehomeRecorder.lex",
	"\\Device\\SystemExtLink\\20445100\\L.AvatarEditor.xex.common.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.AvatarEditor.xex.controlp.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.AvatarEditor.xex.MEDIA.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.BiometricSetup.xex.biometri.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.CreateProfile.xex.cp.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.FamilyCenter.xex.familyce.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.FamilyCenter.xex.familyco.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.FamilyWizard.lex.xzp.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.FieldCalibration.lex.fieldxzp.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.LF.GamerTagChange.lex.DashUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.MP.AccountMgmt.lex.DashUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.MP.ContentExplorer.lex.DashUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.MP.Core.xex.SharedUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.MP.LiveSignup.lex.DashUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.MP.LiveSignup.lex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.MP.MicrosoftStore.lex.CntryUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.MP.MicrosoftStore.lex.DashUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.MP.Purchase.lex.DashUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.natalpregame.xex.natalpre.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.NetworkStorage.lex.xzp.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.NuiTroubleshooter.lex.nuitsxzp.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.OnlineCommon.lex.ekmedia.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.OnlineCommon.lex.vkmedia.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.PrivacyUI.xex.privacyu.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.Search.lex.dashsear.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.Search.xex.dashsear.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Dash.Social.lex.xzp.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.arcade.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.consoles.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.contui.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.dashmain.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.download.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.dvd.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.epix.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.gamer.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.gamercar.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.hubui.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.iptv.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.memory.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.music.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.network.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.oobe.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.parental.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.pictures.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.signinpr.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.signupbo.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.slots.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.socxzp.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.thermal.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dash.xex.videos.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.dashnui.xex.speechpa.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.Fitness.xex.fitness.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.CSVTrans.xex.CSVTrans.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.deviceselector.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.GamerProfile.xex.gp.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.AccountRecovery.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.AccountRecovery.xex.shdmedia.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.AvatarMiniCreator.xex.avatarmc.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.Beacons.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.ChatAndMessenger.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.Friends.xex.friends.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Download.xex.HudDLUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Download.xex.SharedUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.MP.LiveAccount.xex.HudLAUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.MP.NuiPurchase.xex.HudPurUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Payment.xex.HudPayUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.MP.PaymentInst.xex.HudPiUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.MP.PaymentInst.xex.SharedUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Purchase.xex.HudPurUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Subscriptions.xex.HudSubUI.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.NetworkStorage.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.NuiCommunity.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.NuiTroubleshooter.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.PlayerFeedback.xex.Feedback.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.SocialPost.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.TFA.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Guide.Voicemail.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.hud.xex.hud.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.huduiskin.xex.xam.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.LiveSignup.xex.media1.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.MiniMediaPlayer.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.nuihud.xex.media.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.signin.xex.signin.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.Title.NewLiveSignup.xex.app.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.updater.xex.updater.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.xam.xex.controlp.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.xam.xex.gamercrd.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.xam.xex.mplayer.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.xam.xex.shrdres.xzp",
	"\\Device\\SystemExtLink\\20445100\\L.xam.xex.xam.xzp",
	"\\Device\\SystemExtLink\\20445100\\XenonSCLatin.xtt"
]

UPD_FILES_TO_RENAME = [
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Fonts\\Arial_16.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Dolphin\\Media\\Fonts\\Arial_16.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Fonts\\Arial_16.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Fonts\\Arial_16.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Help\\Help.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Help\\Help.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\BackdropDepthVS.xvu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\LightShafts\\Media\\Shaders\\ObjectDepthVS.xvu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AudioConsole3\\Media\\Help\\Help.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SceneViewer2\\Media\\Help\\Help.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Help\\Help.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Media\\Help\\Help.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Database.xmplr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\Database.xmplr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\NuiIdentity.bin.be", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSpeechRecognition\\NuiIdentity.bin.be"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Effects\\SimpleShaders.fxobj", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Effects\\SimpleShaders.fxobj"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Fonts\\Arial_16.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Fonts\\Arial_16.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Help\\Help.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Media\\Help\\Help.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Database.xmplr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\Database.xmplr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\NuiIdentity.bin.be", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\MenuUsingHandles\\NuiIdentity.bin.be"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Effects\\SimpleShaders.fxobj", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Effects\\SimpleShaders.fxobj"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Fonts\\Arial_16.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Fonts\\Arial_16.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Help\\Help.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Help\\Help.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Database.xmplr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Database.xmplr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\NuiIdentity.bin.be", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\NuiIdentity.bin.be"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Effects\\SimpleShaders.fxobj", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Effects\\SimpleShaders.fxobj"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Fonts\\Arial_16.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Fonts\\Arial_16.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Help\\Help.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Help\\Help.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\background_ps.xpu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Shaders\\background_ps.xpu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\background_vs.xvu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Shaders\\background_vs.xvu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_opaque_ps.xpu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Shaders\\body_opaque_ps.xpu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_shiny_opaque_ps.xpu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Shaders\\body_shiny_opaque_ps.xpu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_shiny_transparent_ps.xpu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Shaders\\body_shiny_transparent_ps.xpu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_shiny_vs.xvu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Shaders\\body_shiny_vs.xvu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_transparent_ps.xpu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Shaders\\body_transparent_ps.xpu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\body_vs.xvu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Shaders\\body_vs.xvu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\head_opaque_ps.xpu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Shaders\\head_opaque_ps.xpu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\PlayspaceFeedback\\Media\\Shaders\\head_opaque_vs.xvu", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Media\\Shaders\\head_opaque_vs.xvu"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Database.xmplr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\Database.xmplr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\NuiIdentity.bin.be", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\AvatarRetargeting\\NuiIdentity.bin.be"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Effects\\SimpleShaders.fxobj", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Filtering\\Media\\Effects\\SimpleShaders.fxobj"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Fonts\\Arial_16.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Filtering\\Media\\Fonts\\Arial_16.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Help\\Help.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Filtering\\Media\\Help\\Help.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Database.xmplr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Filtering\\Database.xmplr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\NuiIdentity.bin.be", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\Filtering\\NuiIdentity.bin.be"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Fonts\\Arial_16.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Fonts\\Arial_16.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Media\\Help\\Help.xpr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Media\\Help\\Help.xpr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\Database.xmplr", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\Database.xmplr"),
	("\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\SimpleSkeletonTracking\\NuiIdentity.bin.be", "\\Device\\Harddisk0\\Partition1\\Devkit\\Samples\\DepthMapParticleStream\\NuiIdentity.bin.be"),
	("\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\Database.xmplr", "\\Device\\Harddisk0\\Partition1\\DEVKIT\\identity\\Database.xmplr"),
	("\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\NuiIdentity.bin.be", "\\Device\\Harddisk0\\Partition1\\DEVKIT\\identity\\NuiIdentity.bin.be"),
	("\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\Database.xmplr", "\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\Database.xmplr"),
	("\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\NuiIdentity.bin.be", "\\Device\\Harddisk0\\Partition1\\DEVKIT\\speechLab\\NuiIdentity.bin.be"),
	("\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\Database.xmplr", "\\Device\\Harddisk0\\Partition1\\DEVKIT\\NuiVoiceCollection\\Database.xmplr"),
	("\\Device\\Harddisk0\\Partition1\\DEVKIT\\nuiview\\NuiIdentity.bin.be", "\\Device\\Harddisk0\\Partition1\\DEVKIT\\NuiVoiceCollection\\NuiIdentity.bin.be"),
	("\\Device\\SystemExtLink\\20445100\\L.AvatarEditor.xex.controlp.xzp", "\\Device\\SystemExtLink\\20445100\\L.BiometricSetup.xex.controlp.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.FamilyCenter.xex.familyco.xzp", "\\Device\\SystemExtLink\\20445100\\L.Dash.FamilyWizard.lex.familyco.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.MP.LiveSignup.lex.media.xzp", "\\Device\\SystemExtLink\\20445100\\L.Dash.MP.MicrosoftStore.lex.media.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.FamilyCenter.xex.familyco.xzp", "\\Device\\SystemExtLink\\20445100\\L.Dash.PrivacyUI.xex.familyco.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.OnlineCommon.lex.vkmedia.xzp", "\\Device\\SystemExtLink\\20445100\\L.Dash.Search.lex.vkmedia.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.OnlineCommon.lex.vkmedia.xzp", "\\Device\\SystemExtLink\\20445100\\L.Dash.Search.xex.vkmedia.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.AvatarEditor.xex.controlp.xzp", "\\Device\\SystemExtLink\\20445100\\L.dash.xex.controlp.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.AvatarEditor.xex.common.xzp", "\\Device\\SystemExtLink\\20445100\\L.dash.xex.dashcomm.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.MP.Core.xex.SharedUI.xzp", "\\Device\\SystemExtLink\\20445100\\L.dash.xex.SharedUI.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.AvatarEditor.xex.common.xzp", "\\Device\\SystemExtLink\\20445100\\L.DvdXPlayer.xex.dashcomm.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.dash.xex.dvd.xzp", "\\Device\\SystemExtLink\\20445100\\L.DvdXPlayer.xex.dvd.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Download.xex.SharedUI.xzp", "\\Device\\SystemExtLink\\20445100\\L.Guide.MP.LiveAccount.xex.SharedUI.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Download.xex.SharedUI.xzp", "\\Device\\SystemExtLink\\20445100\\L.Guide.MP.NuiPurchase.xex.SharedUI.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Download.xex.SharedUI.xzp", "\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Payment.xex.SharedUI.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Download.xex.SharedUI.xzp", "\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Purchase.xex.SharedUI.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Download.xex.SharedUI.xzp", "\\Device\\SystemExtLink\\20445100\\L.Guide.MP.Subscriptions.xex.SharedUI.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.AvatarEditor.xex.controlp.xzp", "\\Device\\SystemExtLink\\20445100\\L.LiveSignup.xex.controlp.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.MP.MicrosoftStore.lex.CntryUI.xzp", "\\Device\\SystemExtLink\\20445100\\L.LiveSignup.xex.media2.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.MP.LiveSignup.lex.media.xzp", "\\Device\\SystemExtLink\\20445100\\L.Title.NewLiveSignup.xex.ccapp.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.AvatarEditor.xex.controlp.xzp", "\\Device\\SystemExtLink\\20445100\\L.Title.NewLiveSignup.xex.controlp.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.OnlineCommon.lex.ekmedia.xzp", "\\Device\\SystemExtLink\\20445100\\L.Title.NewLiveSignup.xex.embedded.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Guide.AccountRecovery.xex.shdmedia.xzp", "\\Device\\SystemExtLink\\20445100\\L.Title.NewLiveSignup.xex.media.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.MP.MicrosoftStore.lex.CntryUI.xzp", "\\Device\\SystemExtLink\\20445100\\L.Title.NewLiveSignup.xex.media2.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.OnlineCommon.lex.vkmedia.xzp", "\\Device\\SystemExtLink\\20445100\\L.Title.NewLiveSignup.xex.vkmedia.xzp"),
	("\\Device\\SystemExtLink\\20445100\\L.Dash.OnlineCommon.lex.vkmedia.xzp", "\\Device\\SystemExtLink\\20445100\\L.vk.xex.vk.xzp")
]

def format_response(command: bytes | bytearray, lowercase: bool = False):
	command =  command.decode("UTF8").rstrip()
	if lowercase:
		command = command.lower()
	return command

def xbdm_to_device_path(path: str) -> str:
	if path.startswith("\\Device\\"):
		path = path[len("\\Device\\"):]
	elif path.startswith("\\"):
		path = path[1:]

	p = Path(XBDM_DIR)
	p /= path.replace(":\\", "/").replace("\\", "/")
	p = p.absolute()
	# p.parent.mkdir(parents=True, exist_ok=True)
	return str(p)

def dt_to_filetime(dt):
	if (dt.tzinfo is None) or (dt.tzinfo.utcoffset(dt) is None):
		dt = dt.replace(tzinfo=UTC())
	ft = EPOCH_AS_FILETIME + (timegm(dt.timetuple()) * HUNDREDS_OF_NANOSECONDS)
	return ft + (dt.microsecond * 10)

def creation_time_to_file_time(path: str) -> int:
	#dt = datetime.utcfromtimestamp(getctime(path))
	return dt_to_filetime(datetime.utcnow())

def uint64_to_uint32(num: int, as_hex: bool = False, as_bytes: bool = False) -> tuple | list:
	i = unpack("<II", pack("<Q", num))
	if as_hex:
		low = "0x" + pack("!I", i[0]).hex()
		high = "0x" + pack("!I", i[1]).hex()
		if as_bytes:
			return [bytes(low, "utf8"), bytes(high, "utf8")]
		return [low, high]
	return i

class UTC(tzinfo):
	def utcoffset(self, dt):
		return ZERO

	def tzname(self, dt):
		return "UTC"

	def dst(self, dt):
		return ZERO

class XBDMResponseStatus(IntEnum):
	OK = 200
	MULTILINE = 202
	BINARY = 203
	SENDBINARYDATA = 204
	ERROR = 405

class XBDMShlex(shlex):
	def __init__(self, *args, **kwargs):
		kwargs["posix"] = True
		super(XBDMShlex, self).__init__(*args, **kwargs)
		self.escape = ""  #remove the \ escape
		self.whitespace_split = True

class XBDMParam:
	def __init__(self, value: Any):
		self.value = value

	def __int__(self) -> int:
		return self.as_int()

	def __str__(self) -> str:
		return self.as_str()

	def __bytes__(self) -> bytes:
		return self.as_bytes()

	def is_none(self) -> bool:
		return self.value is None

	def as_int(self) -> int:
		if isinstance(self.value, str):
			if self.value.startswith("0x"):
				return int.from_bytes(bytes.fromhex(self.value[2:].rjust(8, "0")), "big")
		return int(self.value)

	def as_bool(self) -> bool:
		return self.as_str().lower() in ["true", "1"]

	def as_str(self) -> str:
		return str(self.value)

	def as_bytes(self) -> bytes:
		return bytes.fromhex(self.value)

class XBDMCommand:
	name = None
	code = 0
	args = dict()
	flags = []
	formatted = None

	def __init__(self):
		self.reset()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		pass

	def reset(self) -> None:
		self.name = None
		self.code = 0
		self.args = dict()
		self.flags = []
		self.formatted = None

	@staticmethod
	def parse(command: str):
		sh = XBDMShlex(command)
		command = list(sh)
		cmd = XBDMCommand()
		match = CODE_EXP.match(command[0])
		if match:  # response
			cmd.set_code(int(match.group(1)))
		else:  # command
			cmd.set_name(command[0])
		if len(command) > 1:
			for single in command[1:]:
				if "=" in single:
					(key, value) = single.split("=", 1)
					cmd.set_param(key, value)
				else:
					if not cmd.flag_exists(single):
						cmd.set_flag(single)
		return cmd

	def set_name(self, name: str) -> None:
		self.name = name

	def set_code(self, code: int) -> None:
		# self.name = str(code) + "-"
		self.code = code

	def get_code(self) -> int:
		return self.code

	def get_flags(self) -> list[str]:
		return self.flags

	def flag_exists(self, key: str) -> bool:
		return key.lower() in self.flags

	def param_exists(self, key: str, lc_check: bool = False) -> bool:
		return not self.get_param(key, lc_check).is_none()

	def set_flag(self, key: str) -> Any:
		return self.flags.append(key.lower())

	def set_param(self, key: str, value: str | int | bytes | bytearray | bool, quoted: bool = False) -> XBDMParam:
		key = key.lower()
		if isinstance(value, bytes) or isinstance(value, bytearray):
			value = value.decode("UTF8")
		elif quoted:
			value = "\"" + value + "\""
		elif isinstance(value, str):
			value = value
		elif isinstance(value, int):
			value = "0x" + value.to_bytes(4, "big").hex()
		elif isinstance(value, bool):
			value = "1" if value else "0"
		self.args[key] = value
		return XBDMParam(value)

	def get_params(self) -> dict:
		return self.args

	def get_param(self, key: str, lc_check: bool = False) -> XBDMParam:
		key = key.lower()
		val = self.args.get(key)
		if lc_check and val is None:
			val = self.args.get(key)
		return XBDMParam(val)

	def get_output(self, as_bytes: bool = False, line_ending: bool = True) -> str | bytes | bytearray:
		o = ""
		if self.name is not None:  # commands only
			o = self.name
		if self.code is not None and self.code != 0:  # replies only
			o = str(self.code) + "-"
		if len(self.args) > 0:
			o += " "
			o += " ".join([(key + "=" + value) for (key, value) in self.args.items()])
		if len(self.flags) > 0:
			o += " "
			o += " ".join(self.flags)
		if line_ending:
			o += "\r\n"
		if as_bytes:
			return o.encode("UTF8")
		# self.reset()
		return o

class CRC32:
	iv: int = 0
	poly: int = 0
	value: int = 0
	table: list = []

	def __init__(self, iv: int, poly: int):
		self.reset()
		self.iv = iv
		self.poly = poly

		self.compute_table()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		pass

	def reset(self) -> None:
		self.iv = 0
		self.poly = 0
		self.value = 0
		self.table = []

	def compute_table(self) -> None:
		for byt in range(256):
			crc = 0
			for bit in range(8):
				if (byt ^ crc) & 1:
					crc = (crc >> 1) ^ self.poly
				else:
					crc >>= 1
				byt >>= 1
			self.table.append(crc & 0xFFFFFFFF)

	def process(self, data: bytes | bytearray) -> int:
		if self.value == 0:
			self.value = self.iv
		for b in data:
			self.value = self.table[(b ^ self.value) & 0xFF] ^ (self.value >> 8)
		return self.value & 0xFFFFFFFF

async def open_xbdm_connection() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
	(reader, writer) = await asyncio.open_connection(XBDM_HOST, XBDM_PORT)

	# receive 201- connected
	data = await reader.read(XBDM_BUFF_SIZE)
	pkt0 = XBDMCommand.parse(format_response(data))

	assert pkt0.code == 201

	return (reader, writer)

async def close_xbdm_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
	# send bye
	writer.write(b"BYE\r\n")
	await writer.drain()

	# receive 200- bye
	data = await reader.read(XBDM_BUFF_SIZE)
	pkt2 = XBDMCommand.parse(format_response(data))

	assert pkt2.code == 200

	writer.close()

async def send_xbdm_command(cmd: XBDMCommand) -> XBDMCommand:
	(reader, writer) = await open_xbdm_connection()

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.read(XBDM_BUFF_SIZE)
	pkt1 = XBDMCommand.parse(format_response(data))

	if cmd.name in ["recovery", "magicboot"]:
		writer.close()
	else:
		await close_xbdm_connection(reader, writer)

	# return response packet
	return pkt1

async def send_xbdm_upload_file(local_path: str, remote_path: str) -> None:
	p = Path(local_path)

	assert p.exists() and p.is_file()

	(reader, writer) = await open_xbdm_connection()

	fs = p.stat().st_size
	with p.open("rb") as f:
		cmd = XBDMCommand()
		cmd.set_name("SENDFILE")
		cmd.set_param("NAME", remote_path, True)
		cmd.set_param("LENGTH", fs)

		print(cmd.get_output(False, False))

		# send command
		writer.write(cmd.get_output(True))
		await writer.drain()

		# receive response
		data = await reader.read(XBDM_BUFF_SIZE)
		pkt1 = XBDMCommand.parse(format_response(data))

		assert pkt1.code == 204

		# send file data
		while True:
			data = f.read(XBDM_BUFF_SIZE)
			if not data:
				break
			writer.write(data)
			await writer.drain()

	# receive response
	data = await reader.read(XBDM_BUFF_SIZE)
	pkt2 = XBDMCommand.parse(format_response(data))

	assert pkt2.code == 200

	await close_xbdm_connection(reader, writer)

async def send_xbupd_upload_file(local_path: str, remote_path: str) -> None:
	p = Path(local_path)

	assert p.exists() and p.is_file()

	(reader, writer) = await open_xbdm_connection()

	(ctime_low, ctime_high) = uint64_to_uint32(creation_time_to_file_time(str(p)), True)

	fs = p.stat().st_size
	with p.open("rb") as f:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!sysfileupd")
		cmd.set_param("name", remote_path, True)
		cmd.set_param("size", fs)
		cmd.set_param("ftimelo", ctime_low)
		cmd.set_param("ftimehi", ctime_high)

		if remote_path.count("\\") == 1:  # root path
			cmd.set_flag("bootstrap")

		with CRC32(0xFFFFFFFF, 0xEDB88320) as c:
			while True:
				data = f.read(XBDM_BUFF_SIZE)
				if not data:
					break
				c.process(data)
			cmd.set_param("crc", c.value)

		f.seek(0)

		print(cmd.get_output(False, False))

		# send command
		writer.write(cmd.get_output(True))
		await writer.drain()

		# receive response
		data = await reader.read(XBDM_BUFF_SIZE)
		pkt1 = XBDMCommand.parse(format_response(data))

		assert pkt1.code == 204

		# send file data
		while True:
			data = f.read(XBDM_BUFF_SIZE)
			if not data:
				break
			writer.write(data)
			await writer.drain()

	# receive response
	data = await reader.read(XBDM_BUFF_SIZE)
	pkt2 = XBDMCommand.parse(format_response(data))

	assert pkt2.code == 200

	await close_xbdm_connection(reader, writer)

async def send_xbupd_delete_file(remote_path: str) -> XBDMCommand:
	(reader, writer) = await open_xbdm_connection()

	# create command
	cmd = XBDMCommand()
	cmd.set_name("xbupdate!sysfileupd")
	cmd.set_param("name", remote_path, True)
	cmd.set_param("remove", "1")

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.read(XBDM_BUFF_SIZE)
	pkt1 = XBDMCommand.parse(format_response(data))

	assert pkt1.code == 200

	await close_xbdm_connection(reader, writer)

	# return response packet
	return pkt1

async def send_xbupd_delete_dir(remote_path: str) -> XBDMCommand:
	(reader, writer) = await open_xbdm_connection()

	# create command
	cmd = XBDMCommand()
	cmd.set_name("xbupdate!sysfileupd")
	cmd.set_param("name", remote_path, True)
	cmd.set_param("removedir", "1")

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.read(XBDM_BUFF_SIZE)
	pkt1 = XBDMCommand.parse(format_response(data))

	assert pkt1.code == 200

	await close_xbdm_connection(reader, writer)

	# return response packet
	return pkt1

async def send_xbupd_rename_file(remote_path_old: str, remote_path_new: str) -> XBDMCommand:
	(reader, writer) = await open_xbdm_connection()

	# create command
	cmd = XBDMCommand()
	cmd.set_name("xbupdate!sysfileupd")
	cmd.set_param("name", remote_path_new, True)
	cmd.set_param("localsrc", remote_path_old, True)

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.read(XBDM_BUFF_SIZE)
	pkt1 = XBDMCommand.parse(format_response(data))

	assert pkt1.code == 200

	await close_xbdm_connection(reader, writer)

	# return response packet
	return pkt1

async def xbdm_recovery_client():
	# send latest xbupdate.xex to the console
	await send_xbdm_upload_file(xbdm_to_device_path("\\Device\\Flash\\xbupdate.xex"), "\\Device\\Flash\\xbupdate.xex")

	cmd = XBDMCommand()
	cmd.set_name("recovery")
	await send_xbdm_command(cmd)

	print("Waiting 30 seconds for recovery to boot...")
	await asyncio.sleep(30)

	cmd.reset()
	cmd.set_name("xbupdate!drawtext")
	cmd.set_param("text", "UwU", True)
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!version")
	cmd.set_param("verhi", 0x20000)
	cmd.set_param("verlo", 0x53080012)
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.set_name("xbupdate!validdevice")
	cmd.set_param("basesysver", "1888")
	cmd.set_param("mbneeded", "210")
	print(cmd.get_output(False, False))
	rep = await send_xbdm_command(cmd)
	print(rep.get_output(False, False))

	valid = rep.get_param("valid").as_bool()
	devidx = rep.get_param("deviceindex").as_int()

	assert valid, "No valid device found to write recovery to!"

	cmd.reset()
	cmd.set_name("xbupdate!validatehddpartitions")
	print(cmd.get_output(False, False))
	rep = await send_xbdm_command(cmd)
	print(rep.get_output(False, False))

	valid = rep.get_param("valid").as_bool()

	assert valid, "No valid device found to write recovery to!"

	cmd.reset()
	cmd.set_name("xbupdate!isflashclean")
	print(cmd.get_output(False, False))
	rep = await send_xbdm_command(cmd)
	print(rep.get_output(False, False))

	valid = rep.flag_exists("TRUE")

	assert valid, "Flash isn't clean!"

	cmd.reset()
	cmd.set_name("xbupdate!instrecoverytype")
	print(cmd.get_output(False, False))
	rep = await send_xbdm_command(cmd)
	print(rep.get_output(False, False))

	rectyp = rep.get_param("recoverytype").as_int()
	hres = rep.get_param("hresult").as_int()

	assert rectyp, "Invalid recovery type!"

	cmd.reset()
	cmd.set_name("xbupdate!version")
	cmd.set_param("verhi", 0x20000)
	cmd.set_param("verlo", 0x53080012)
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!configure")
	cmd.set_param("flashstart", 0x200000)
	cmd.set_flag("ffs")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!recovery")
	cmd.set_param("installver", "17489")
	cmd.set_param("selectedver", "17489")
	cmd.set_param("autoupd", "0")
	cmd.set_param("rectype", "1")
	cmd.set_param("deviceindex", str(devidx))
	cmd.set_flag("noformathdd")
	cmd.set_flag("formatulrcache")
	cmd.set_flag("formatsysext")
	cmd.set_flag("createsysextrd")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	# delete files
	for remote_path in UPD_FILES_TO_DELETE:
		await send_xbupd_delete_file(remote_path)

	# delete directories
	for remote_path in UPD_DIRS_TO_DELETE:
		await send_xbupd_delete_dir(remote_path)

	# upload files
	# shadowboot
	await  send_xbupd_upload_file(SHADOWBOOT_PATH, "\\Device\\Harddisk0\\Partition1\\xboxrom_update.bin")
	# system files
	for remote_path in UPD_FILES_TO_UPLOAD:
		await send_xbupd_upload_file(xbdm_to_device_path(remote_path), remote_path)
	# aux and ext
	#for remote_path in UPD_FILES_TO_UPLOAD_AUX_EXT:
	#	await send_xbupd_upload_file(xbdm_to_device_path(remote_path), remote_path)
	# samples
	#for remote_path in UPD_FILES_TO_UPLOAD_SAMPLES:
	#	await send_xbupd_upload_file(xbdm_to_device_path(remote_path), remote_path)

	# rename files
	#for (remote_path_old, remote_path_new) in UPD_FILES_TO_RENAME:
	#	await send_xbupd_rename_file(remote_path_old, remote_path_new)

	# all the other commands
	cmd.reset()
	cmd.set_name("xbupdate!close")
	cmd.set_flag("final")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!flash")
	cmd.set_param("romdir", "\\Device\\Harddisk0\\Partition3\\ROM", True)
	cmd.set_flag("enum")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!flash")
	cmd.set_param("romdir", "\\Device\\Harddisk0\\Partition3\\ROM\\0000", True)
	cmd.set_flag("query")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!commitsysextramdisk")
	cmd.set_param("deviceindex", str(devidx))
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!getregion")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!setxamfeaturemask")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.set_name("xbupdate!finish")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.set_name("xbupdate!restart")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.set_name("magicboot")
	cmd.set_flag("cold")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

def main() -> int:
	global XBDM_HOST, SHADOWBOOT_PATH

	parser = ArgumentParser(description="A script to recover Xbox 360 devkits")
	parser.add_argument("host", type=str, help="The devkit IP address")
	parser.add_argument("image", type=str, help="The shadowboot image to install to flash")
	args = parser.parse_args()

	XBDM_HOST = args.host
	SHADOWBOOT_PATH = args.image

	assert Path(SHADOWBOOT_PATH).is_file(), "Shadowboot image doesn't exist!"

	asyncio.run(xbdm_recovery_client())

	return 0

if __name__ == "__main__":
	exit(main())