# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2021 Neongecko.com Inc. | All Rights Reserved
#
# Notice of License - Duplicating this Notice of License near the start of any file containing
# a derivative of this software is a condition of license for this software.
# Friendly Licensing:
# No charge, open source royalty free use of the Neon AI software source and object is offered for
# educational users, noncommercial enthusiasts, Public Benefit Corporations (and LLCs) and
# Social Purpose Corporations (and LLCs). Developers can contact developers@neon.ai
# For commercial licensing, distribution of derivative works or redistribution please contact licenses@neon.ai
# Distributed on an "AS IS” basis without warranties or conditions of any kind, either express or implied.
# Trademarks of Neongecko: Neon AI(TM), Neon Assist (TM), Neon Communicator(TM), Klat(TM)
# Authors: Guy Daniels, Daniel McKnight, Regina Bloomstine, Elon Gasper, Richard Leeds
#
# Specialized conversational reconveyance options from Conversation Processing Intelligence Corp.
# US Patents 2008-2021: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending

import shutil
import unittest
from threading import Event
from time import sleep

import pytest

from os import mkdir
from os.path import dirname, join, exists
from mock import Mock
from mycroft_bus_client import Message
from ovos_utils.messagebus import FakeBus


class TestSkill(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        from mycroft.skills.skill_loader import SkillLoader

        cls.bus = FakeBus()
        cls.bus.run_in_thread()
        skill_loader = SkillLoader(cls.bus, dirname(dirname(__file__)))
        skill_loader.load()
        cls.skill = skill_loader.instance
        cls.test_fs = join(dirname(__file__), "skill_fs")
        if not exists(cls.test_fs):
            mkdir(cls.test_fs)
        cls.skill.settings_write_path = cls.test_fs
        cls.skill.file_system.path = cls.test_fs

        # cls.skill._init_settings()
        # cls.skill.initialize()
        # Override speak and speak_dialog to test passed arguments
        cls.skill.speak = Mock()
        cls.skill.speak_dialog = Mock()
        cls.skill.schedule_event = Mock()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.test_fs)

    def tearDown(self) -> None:
        self.skill.speak.reset_mock()
        self.skill.speak_dialog.reset_mock()
        self.skill.schedule_event.reset_mock()

    def test_00_skill_init(self):
        # Test any parameters expected to be set in init or initialize methods
        from neon_utils.skills import NeonSkill

        self.assertIsInstance(self.skill, NeonSkill)
        self.assertIsInstance(self.skill.query_replies, dict)
        self.assertIsInstance(self.skill.query_extensions, dict)
        self.assertIsNotNone(self.skill.lock)

        listeners = self.skill.bus.ee.listeners

        self.assertEqual(len(listeners(
            "communication:request.message.response")), 1)

        self.assertIsNotNone(len(listeners(
            "communication:request.call.response")), 1)

    def test_handle_place_call(self):
        real_timeout = self.skill._place_call_timeout
        self.skill._place_call_timeout = Mock()
        handled_event = Event()
        valid_response_data = {"request": "valid_contact",
                               "skill_id": "test_skill_id",
                               "callback_data": {"test": "data"}}

        def handle_place_call(message: Message):
            if message.data["request"] == "valid_contact":
                self.bus.emit(message.reply(
                    "communication:request.call.response",
                    {"request": message.data["request"],
                     "searching": True,
                     "skill_id": "test_skill_id"}))
                sleep(1)
                self.bus.emit(message.reply(
                    "communication:request.call.response",
                    valid_response_data
                ))
                sleep(1)
            elif message.data["request"] == "valid_extension":
                self.bus.emit(message.reply(
                    "communication:request.call.response",
                    {"request": message.data["request"],
                     "searching": True,
                     "skill_id": "test_skill_id"}))
            elif message.data["request"] == "invalid_contact":
                pass
            sleep(2)
            handled_event.set()

        self.bus.on("communication:request.call", handle_place_call)

        valid_message = Message("test", {"utterance": "test",
                                         "contact": "valid_contact"},
                                {"neon_should_respond": True})
        valid_extension = Message("test", {"utterance": "test",
                                           "contact": "valid_extension"},
                                  {"neon_should_respond": True})
        invalid_message = Message("test", {"utterance": "test",
                                           "contact": "invalid_contact"},
                                  {"neon_should_respond": True})

        self.skill.handle_place_call(valid_message)
        handled_event.wait()
        self.assertEqual(self.skill.query_extensions["valid_contact"], [])
        self.assertEqual(self.skill.query_replies["valid_contact"],
                         [valid_response_data])
        self.assertEqual(self.skill.schedule_event.call_count, 3)
        self.skill.schedule_event.reset_mock()

        self.skill.handle_place_call(valid_extension)
        handled_event.wait()
        self.assertEqual(self.skill.query_extensions["valid_extension"],
                         ["test_skill_id"])
        self.assertEqual(self.skill.query_replies["valid_extension"],
                         [])
        self.assertEqual(self.skill.schedule_event.call_count, 2)
        self.skill.schedule_event.reset_mock()

        self.skill.handle_place_call(invalid_message)
        handled_event.wait()
        self.skill.schedule_event.assert_called_once()
        call_args = self.skill.schedule_event.call_args
        self.assertEqual(call_args[0][0], self.skill._place_call_timeout)
        self.assertEqual(call_args[0][1], 1)
        self.assertIsInstance(call_args[1]["data"], dict)
        self.assertEqual(call_args[1]["name"], "PlaceCallTimeout")
        self.assertEqual(self.skill.query_extensions["invalid_contact"],
                         [])
        self.assertEqual(self.skill.query_replies["invalid_contact"],
                         [])

        self.bus.remove("communication:request.call", handle_place_call)
        self.skill._place_call_timeout = real_timeout

    def test_handle_send_message(self):
        real_timeout = self.skill._send_message_timeout
        self.skill._send_message_timeout = Mock()
        handled_event = Event()
        valid_response_data = {"request": "valid test",
                               "skill_id": "test_skill_id",
                               "callback_data": {"test": "data"}}

        def handle_send_message(message: Message):
            if message.data["request"] == "valid test":
                self.bus.emit(message.reply(
                    "communication:request.message.response",
                    {"request": message.data["request"],
                     "searching": True,
                     "skill_id": "test_skill_id"}))
                sleep(1)
                self.bus.emit(message.reply(
                    "communication:request.message.response",
                    valid_response_data
                ))
                sleep(1)
            elif message.data["request"] == "valid extension":
                self.bus.emit(message.reply(
                    "communication:request.message.response",
                    {"request": message.data["request"],
                     "searching": True,
                     "skill_id": "test_skill_id"}))
            elif message.data["request"] == "invalid test":
                pass
            sleep(2)
            handled_event.set()

        self.bus.on("communication:request.message", handle_send_message)

        valid_message = Message("test", {"utterance": "valid test"},
                                {"neon_should_respond": True})
        valid_extension = Message("test", {"utterance": "neon valid extension",
                                           "neon": "neon"},
                                  {"neon_should_respond": True})
        invalid_message = Message("test", {"utterance": "invalid test"},
                                  {"neon_should_respond": True})

        self.skill.handle_send_message(valid_message)
        handled_event.wait()
        self.assertEqual(self.skill.query_extensions["valid test"], [])
        self.assertEqual(self.skill.query_replies["valid test"],
                         [valid_response_data])
        self.assertEqual(self.skill.schedule_event.call_count, 3)
        self.skill.schedule_event.reset_mock()

        self.skill.handle_send_message(valid_extension)
        handled_event.wait()
        self.assertEqual(self.skill.query_extensions["valid extension"],
                         ["test_skill_id"])
        self.assertEqual(self.skill.query_replies["valid extension"],
                         [])
        self.assertEqual(self.skill.schedule_event.call_count, 2)
        self.skill.schedule_event.reset_mock()

        self.skill.handle_send_message(invalid_message)
        handled_event.wait()
        self.skill.schedule_event.assert_called_once()
        call_args = self.skill.schedule_event.call_args
        self.assertEqual(call_args[0][0], self.skill._send_message_timeout)
        self.assertEqual(call_args[0][1], 1)
        self.assertIsInstance(call_args[1]["data"], dict)
        self.assertEqual(call_args[1]["name"], "SendMessageTimeout")
        self.assertEqual(self.skill.query_extensions["invalid test"],
                         [])
        self.assertEqual(self.skill.query_replies["invalid test"],
                         [])

        self.bus.remove("communication:request.message", handle_send_message)
        self.skill._send_message_timeout = real_timeout

    # TODO: Test timeout methods


if __name__ == '__main__':
    pytest.main()
