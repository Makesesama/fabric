# This file has been autogenerated by the pywayland scanner

# Copyright 2020 The River Developers
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

from __future__ import annotations

from pywayland.protocol_core import (Argument, ArgumentType, Global, Interface,
                                     Proxy, Resource)


class ZriverCommandCallbackV1(Interface):
    """Callback object

    This object is created by the run_command request. Exactly one of the
    success or failure events will be sent. This object will be destroyed by
    the compositor after one of the events is sent.
    """

    name = "zriver_command_callback_v1"
    version = 1


class ZriverCommandCallbackV1Proxy(Proxy[ZriverCommandCallbackV1]):
    interface = ZriverCommandCallbackV1


class ZriverCommandCallbackV1Resource(Resource):
    interface = ZriverCommandCallbackV1

    @ZriverCommandCallbackV1.event(
        Argument(ArgumentType.String),
    )
    def success(self, output: str) -> None:
        """Command successful

        Sent when the command has been successfully received and executed by
        the compositor. Some commands may produce output, in which case the
        output argument will be a non-empty string.

        :param output:
            the output of the command
        :type output:
            `ArgumentType.String`
        """
        self._post_event(0, output)

    @ZriverCommandCallbackV1.event(
        Argument(ArgumentType.String),
    )
    def failure(self, failure_message: str) -> None:
        """Command failed

        Sent when the command could not be carried out. This could be due to
        sending a non-existent command, no command, not enough arguments, too
        many arguments, invalid arguments, etc.

        :param failure_message:
            a message explaining why failure occurred
        :type failure_message:
            `ArgumentType.String`
        """
        self._post_event(1, failure_message)


class ZriverCommandCallbackV1Global(Global):
    interface = ZriverCommandCallbackV1


ZriverCommandCallbackV1._gen_c()
ZriverCommandCallbackV1.proxy_class = ZriverCommandCallbackV1Proxy
ZriverCommandCallbackV1.resource_class = ZriverCommandCallbackV1Resource
ZriverCommandCallbackV1.global_class = ZriverCommandCallbackV1Global
