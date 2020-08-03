# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2020 Neongecko.com Inc. | All Rights Reserved
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
# US Patents 2008-2020: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending

from threading import Lock
from time import sleep

from adapt.intent import IntentBuilder
from mycroft import MycroftSkill
from mycroft.util import LOG


class CommunicationSkill(MycroftSkill):
    def __init__(self):
        super(CommunicationSkill, self).__init__(name="Communication")
        self.query_replies = {}
        self.query_extensions = {}
        self.lock = Lock()

    def initialize(self):
        self.add_event("communication:request.message.response", self.handle_send_message_response)
        self.add_event("communication:request.call.response", self.handle_place_call_response)

        send_message_intent = IntentBuilder("SendMessageIntent")\
            .optionally("Neon").require("draft").require("message").build()
        self.register_intent(send_message_intent, self.handle_send_message)

        self.register_intent_file("call.intent", self.handle_place_call)

    def handle_place_call(self, message):
        if self.neon_in_request(message):
            if self.check_for_signal('CORE_useHesitation', -1):
                self.speak("Just a moment.")
            utt = message.data.get("utterance")
            request = message.data.get("contact")
            self.query_replies[request] = []
            self.query_extensions[request] = []
            self.bus.emit(message.forward("communication:request.call", data={"utterance": utt,
                                                                              "request": request}))
            # Give skills one second to reply to this request
            self.schedule_event(self._place_call_timeout, 1,
                                data={"request": request},
                                name="PlaceCallTimeout")

    def handle_send_message(self, message):
        if self.neon_in_request(message):
            if self.check_for_signal('CORE_useHesitation', -1):
                self.speak("Just a moment.")
            utt = message.data.get("utterance")
            request = utt.replace(message.data.get("Neon", ""), "")
            self.query_replies[request] = []
            self.query_extensions[request] = []
            self.bus.emit(message.forward("communication:request.message", data={"utterance": utt,
                                                                                 "request": request}))
            # Give skills one second to reply to this request
            self.schedule_event(self._send_message_timeout, 1,
                                data={"request": request},
                                name="SendMessageTimeout")

    def handle_place_call_response(self, message):
        with self.lock:
            request = message.data["request"]
            skill_id = message.data["skill_id"]

            # Skill has requested more time to complete search
            if "searching" in message.data and request in self.query_extensions:
                # Manage requests for time to complete searches
                if message.data["searching"]:
                    # extend the timeout by 5 seconds
                    self.cancel_scheduled_event("PlaceCallTimeout")
                    LOG.debug(f"DM: Timeout in 5s for {skill_id}")
                    self.schedule_event(self._place_call_timeout, 5,
                                        data={"request": request},
                                        name='PlaceCallTimeout')

                    # TODO: Perhaps block multiple extensions?
                    if skill_id not in self.query_extensions[request]:
                        self.query_extensions[request].append(skill_id)
                else:
                    LOG.debug(f"DM: {skill_id} has a response")
                    # Search complete, don't wait on this skill any longer
                    if skill_id in self.query_extensions[request]:
                        self.query_extensions[request].remove(skill_id)
                        LOG.debug(f"DM: test {self.query_extensions[request]}")
                        if not self.query_extensions[request]:
                            self.cancel_scheduled_event("PlaceCallTimeout")
                            LOG.debug("DM: Timeout in 1s")
                            self.schedule_event(self._place_call_timeout, 1,
                                                data={"request": request},
                                                name='PlaceCallTimeout')

            elif request in self.query_replies:
                # Collect all replies until the timeout
                self.query_replies[request].append(message.data)
                # Search complete, don't wait on this skill any longer
                if skill_id in self.query_extensions[request]:
                    self.query_extensions[request].remove(skill_id)
                    if not self.query_extensions[request]:
                        self.cancel_scheduled_event("PlaceCallTimeout")
                        self.schedule_event(self._place_call_timeout, 0,
                                            data={"request": request},
                                            name='PlaceCallTimeout')

    def handle_send_message_response(self, message):
        with self.lock:
            request = message.data["request"]
            skill_id = message.data["skill_id"]

            # Skill has requested more time to complete search
            if "searching" in message.data and request in self.query_extensions:
                # Manage requests for time to complete searches
                if message.data["searching"]:
                    # extend the timeout by 5 seconds
                    self.cancel_scheduled_event("SendMessageTimeout")
                    LOG.debug(f"DM: Timeout in 5s for {skill_id}")
                    self.schedule_event(self._send_message_timeout, 5,
                                        data={"request": request},
                                        name='SendMessageTimeout')

                    # TODO: Perhaps block multiple extensions?
                    if skill_id not in self.query_extensions[request]:
                        self.query_extensions[request].append(skill_id)
                else:
                    LOG.debug(f"DM: {skill_id} has a response")
                    # Search complete, don't wait on this skill any longer
                    if skill_id in self.query_extensions[request]:
                        self.query_extensions[request].remove(skill_id)
                        LOG.debug(f"DM: test {self.query_extensions[request]}")
                        if not self.query_extensions[request]:
                            self.cancel_scheduled_event("SendMessageTimeout")
                            LOG.debug("DM: Timeout in 1s")
                            self.schedule_event(self._send_message_timeout, 1,
                                                data={"request": request},
                                                name='SendMessageTimeout')

            elif request in self.query_replies:
                # Collect all replies until the timeout
                self.query_replies[request].append(message.data)
                # Search complete, don't wait on this skill any longer
                if skill_id in self.query_extensions[request]:
                    self.query_extensions[request].remove(skill_id)
                    if not self.query_extensions[request]:
                        self.cancel_scheduled_event("SendMessageTimeout")
                        self.schedule_event(self._send_message_timeout, 0,
                                            data={"request": request},
                                            name='SendMessageTimeout')

    def _place_call_timeout(self, message):
        LOG.debug(f"DM: TIMEOUT!")
        with self.lock:
            # Prevent any late-comers from retriggering this query handler
            request = message.data["request"]
            self.query_extensions[request] = []

            # Look at any replies that arrived before the timeout
            # Find response(s) with the highest confidence
            best = None
            ties = []
            LOG.debug(f"CommonMessage Resolution for: {request}")
            for handler in self.query_replies[request]:
                LOG.debug(f'{handler["conf"]} using {handler["skill_id"]}')
                if not best or handler["conf"] > best["conf"]:
                    best = handler
                    ties = []
                elif handler["conf"] == best["conf"]:
                    ties.append(handler)

            if best:
                if ties:
                    # TODO: Ask user to pick between ties or do it automagically
                    pass

                LOG.info(f"DM: match={best}")
                # invoke best match
                send_data = {"skill_id": best["skill_id"],
                             "request": best["request"],
                             "skill_data": best["skill_data"]}
                self.bus.emit(message.forward("communication:place.call", send_data))
                # TODO: Handle this in subclassed skills
                # self.gui.show_page("controls.qml", override_idle=True)
                # LOG.info("Playing with: {}".format(best["skill_id"]))
                # start_data = {"skill_id": best["skill_id"],
                #               "phrase": search_phrase,
                #               "callback_data": best.get("callback_data")}
                # self.bus.emit(message.forward('play:start', start_data))
                # self.has_played = True

            else:
                LOG.info("   No matches")
                self.speak_dialog("cant.send", private=True)

            if request in self.query_replies:
                del self.query_replies[request]
            if request in self.query_extensions:
                del self.query_extensions[request]

    def _send_message_timeout(self, message):
        LOG.debug(f"DM: TIMEOUT!")
        with self.lock:
            # Prevent any late-comers from retriggering this query handler
            request = message.data["request"]
            self.query_extensions[request] = []

            # Look at any replies that arrived before the timeout
            # Find response(s) with the highest confidence
            best = None
            ties = []
            LOG.debug(f"CommonMessage Resolution for: {request}")
            for handler in self.query_replies[request]:
                LOG.debug(f'{handler["conf"]} using {handler["skill_id"]}')
                if not best or handler["conf"] > best["conf"]:
                    best = handler
                    ties = []
                elif handler["conf"] == best["conf"]:
                    ties.append(handler)

            if best:
                if ties:
                    # TODO: Ask user to pick between ties or do it automagically
                    pass

                LOG.info(f"DM: match={best}")
                # invoke best match
                send_data = {"skill_id": best["skill_id"],
                             "request": best["request"],
                             "skill_data": best["skill_data"]}
                self.bus.emit(message.forward("communication:send.message", send_data))
                # TODO: Handle this in subclassed skills
                # self.gui.show_page("controls.qml", override_idle=True)
                # LOG.info("Playing with: {}".format(best["skill_id"]))
                # start_data = {"skill_id": best["skill_id"],
                #               "phrase": search_phrase,
                #               "callback_data": best.get("callback_data")}
                # self.bus.emit(message.forward('play:start', start_data))
                # self.has_played = True

            else:
                LOG.info("   No matches")
                self.speak_dialog("cant.send", private=True)

            if request in self.query_replies:
                del self.query_replies[request]
            if request in self.query_extensions:
                del self.query_extensions[request]


def create_skill():
    return CommunicationSkill()
