# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2022 Neongecko.com Inc.
# Contributors: Daniel McKnight, Guy Daniels, Elon Gasper, Richard Leeds,
# Regina Bloomstine, Casimiro Ferreira, Andrii Pernatii, Kirill Hrymailo
# BSD-3 License
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS;  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE,  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from threading import Lock
from adapt.intent import IntentBuilder
from ovos_utils.log import LOG
from ovos_utils import classproperty
from ovos_utils.process_utils import RuntimeRequirements
from neon_utils.skills.neon_skill import NeonSkill
from neon_utils.signal_utils import check_for_signal
from mycroft.skills import intent_handler, intent_file_handler


class CommunicationSkill(NeonSkill):
    def __init__(self):
        super(CommunicationSkill, self).__init__(name="Communication")
        self.query_replies = {}
        self.query_extensions = {}
        self.lock = Lock()

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(network_before_load=False,
                                   internet_before_load=False,
                                   gui_before_load=False,
                                   requires_internet=True,
                                   requires_network=True,
                                   requires_gui=False,
                                   no_internet_fallback=True,
                                   no_network_fallback=False,
                                   no_gui_fallback=True)

    def initialize(self):
        self.add_event("communication:request.call.response",
                       self.handle_place_call_response)
        self.add_event("communication:request.message.response",
                       self.handle_send_message_response)

    @intent_file_handler("call.intent")
    def handle_place_call(self, message):
        if self.neon_in_request(message):
            # TODO: Move hesitation to user preference DM
            if check_for_signal('CORE_useHesitation', -1):
                self.speak_dialog("one_moment")
            utt = message.data.get("utterance")
            request = message.data.get("contact")
            # TODO: This should use a UID, rather than the requested contact DM
            self.query_replies[request] = []
            self.query_extensions[request] = []
            self.bus.emit(message.forward("communication:request.call",
                                          data={"utterance": utt,
                                                "request": request}))
            # Give skills one second to reply to this request
            self.schedule_event(self._place_call_timeout, 1,
                                data={"request": request},
                                name="PlaceCallTimeout")

    @intent_handler(IntentBuilder("SendMessageIntent")
                    .optionally("neon").require("draft").require("message"))
    def handle_send_message(self, message):
        if self.neon_in_request(message):
            if check_for_signal('CORE_useHesitation', -1):
                self.speak_dialog("one_moment")
            utt = message.data.get("utterance")
            # TODO: This should use a UID, rather than the request utterance DM
            request = utt.replace(message.data.get("neon", ""), "").strip()
            self.query_replies[request] = []
            self.query_extensions[request] = []
            self.bus.emit(message.forward("communication:request.message",
                                          data={"utterance": utt,
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
                    LOG.debug(f"Timeout in 5s for {skill_id}")
                    self.schedule_event(self._place_call_timeout, 5,
                                        data={"request": request},
                                        name='PlaceCallTimeout')

                    # TODO: Perhaps block multiple extensions?
                    if skill_id not in self.query_extensions[request]:
                        self.query_extensions[request].append(skill_id)
                else:
                    LOG.debug(f"{skill_id} has a response")
                    # Search complete, don't wait on this skill any longer
                    if skill_id in self.query_extensions[request]:
                        self.query_extensions[request].remove(skill_id)
                        if not self.query_extensions[request]:
                            self.cancel_scheduled_event("PlaceCallTimeout")
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
                    LOG.debug(f"Timeout in 5s for {skill_id}")
                    self.schedule_event(self._send_message_timeout, 5,
                                        data={"request": request},
                                        name='SendMessageTimeout')

                    # TODO: Perhaps block multiple extensions?
                    if skill_id not in self.query_extensions[request]:
                        self.query_extensions[request].append(skill_id)
                else:
                    LOG.debug(f"{skill_id} has a response")
                    # Search complete, don't wait on this skill any longer
                    if skill_id in self.query_extensions[request]:
                        self.query_extensions[request].remove(skill_id)
                        if not self.query_extensions[request]:
                            self.cancel_scheduled_event("SendMessageTimeout")
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

                LOG.info(f"match={best}")
                # invoke best match
                send_data = {"skill_id": best["skill_id"],
                             "request": best["request"],
                             "skill_data": best["skill_data"]}
                self.bus.emit(message.forward("communication:place.call", send_data))

            else:
                LOG.info("   No matches")
                self.speak_dialog("cant_send", private=True)

            if request in self.query_replies:
                del self.query_replies[request]
            if request in self.query_extensions:
                del self.query_extensions[request]

    def _send_message_timeout(self, message):
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

                LOG.info(f"match={best}")
                # invoke best match
                send_data = {"skill_id": best["skill_id"],
                             "request": best["request"],
                             "skill_data": best["skill_data"]}
                self.bus.emit(message.forward("communication:send.message", send_data))
            else:
                LOG.info("   No matches")
                self.speak_dialog("cant_send", private=True)

            if request in self.query_replies:
                del self.query_replies[request]
            if request in self.query_extensions:
                del self.query_extensions[request]


def create_skill():
    return CommunicationSkill()
