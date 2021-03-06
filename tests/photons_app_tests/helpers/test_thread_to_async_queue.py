# coding: spec

from photons_app.test_helpers import AsyncTestCase
from photons_app.errors import PhotonsAppError
from photons_app import helpers as hp

from noseOfYeti.tokeniser.async_support import async_noy_sup_setUp
import threading
import asyncio
import mock
import time
import uuid

describe AsyncTestCase, "ThreadToAsyncQueue":
    async before_each:
        self.stop_fut = asyncio.Future()

    def ttaq(self, num_threads):
        ttaq = hp.ThreadToAsyncQueue(self.stop_fut, num_threads, mock.Mock(name="onerror"))

        class ACM(object):
            async def __aenter__(s):
                await self.wait_for(ttaq.start(), timeout=1)
                return ttaq

            async def __aexit__(s, exc_type, exc, tb):
                await ttaq.finish()

                if exc:
                    exc.__traceback__ = tb
                    # Make sure the error gets risen
                    return False

        return ACM()

    async it "works":
        called = []
        async with self.ttaq(2) as ttaq:
            def action():
                time.sleep(0.03)
                called.append(1)
                return 1
            res = ttaq.request(action)

            def action2():
                called.append(2)
                return 2
            res2 = ttaq.request(action2)

            self.assertEqual(await self.wait_for(res), 1)
            self.assertEqual(await self.wait_for(res2), 2)

            # Proof that action2 wasn't held up by action
            self.assertEqual(called, [2, 1])

    describe "white box testing":
        async before_each:
            # Deliberately don't start the queue so that we can do that stuff manually
            self.ttaq = hp.ThreadToAsyncQueue(self.stop_fut, 1, mock.Mock(name="onerror"))

        describe "request":
            async it "puts the func on the queue ready to be picked up by a thread":
                func = mock.Mock(name="func")
                key = "key"

                assert self.ttaq.queue.empty()
                self.assertEqual(len(self.ttaq.futures), 0)

                with mock.patch("uuid.uuid1", lambda: key):
                    fut = self.ttaq.request(func)

                self.assertEqual(self.ttaq.queue.qsize(), 1)
                thing = self.ttaq.queue.get()

                self.assertEqual(thing, (key, func))
                self.assertIs(self.ttaq.futures[key], fut)

        describe "find_and_set_future":
            async it "does nothing if the key isn't known":
                key = str(uuid.uuid1())
                assert key not in self.ttaq.futures
                self.assertIs(self.ttaq.find_and_set_future(key, mock.Mock(name="result"), mock.Mock(name="exception")), None)

            async it "sets exception on the future if result is Nope":
                key = str(uuid.uuid1())
                fut = asyncio.Future()
                self.ttaq.futures[key] = fut

                result = hp.Nope
                exception = PhotonsAppError("blah")

                assert not fut.done() and not fut.cancelled()
                self.ttaq.find_and_set_future(key, result, exception)

                self.assertIs(fut.exception(), exception)

            async it "otherwise sets result on the future":
                key = str(uuid.uuid1())
                fut = asyncio.Future()
                self.ttaq.futures[key] = fut

                result = mock.Mock(name="result")
                exception = None

                assert not fut.done() and not fut.cancelled()
                self.ttaq.find_and_set_future(key, result, exception)

                self.assertIs(fut.result(), result)

        describe "process":
            async it "calls the procedure and puts result on the result_queue":
                key = str(uuid.uuid1())
                action_result = mock.Mock(name="action_result")

                def action():
                    return action_result

                thread = threading.Thread(target=self.ttaq.process, args=(key, action))
                thread.daemon = True
                thread.start()

                self.assertEqual(await self.wait_for(self.ttaq.result_queue.get()), (key, action_result, hp.Nope))

            async it "gives you the exception when it fails":
                key = str(uuid.uuid1())
                onerror = mock.Mock(name="onerror")
                self.ttaq.onerror = onerror

                error = PhotonsAppError("Much fail")
                called = []

                def action():
                    called.append("action")
                    raise error

                thread = threading.Thread(target=self.ttaq.process, args=(key, action))
                thread.daemon = True
                thread.start()

                self.assertEqual(await self.wait_for(self.ttaq.result_queue.get()), (key, hp.Nope, error))
                self.assertEqual(called, ["action"])
                onerror.assert_called_once_with((PhotonsAppError, error, mock.ANY))
