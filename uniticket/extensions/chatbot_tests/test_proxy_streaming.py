import httpx

from .base import ProxyTestCase


class EventStream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.consumed = []
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            self.consumed.append(chunk)
            yield chunk

    def close(self):
        self.closed = True


class AgUiProxyStreamingTests(ProxyTestCase):
    def setUp(self):
        super().setUp()
        self.events = [b'data: {"type":"RUN_STARTED"}\n\n', b'data: {"type":"RUN_FINISHED"}\n\n']
        self.stream = EventStream(self.events)
        self.upstream = httpx.Response(
            200, headers={"Content-Type": "text/event-stream; charset=utf-8"}, stream=self.stream,
        )

    def assert_connections_closed(self):
        self.assertTrue(self.stream.closed)
        self.assertTrue(self.upstream.is_closed)
        self.assertTrue(self.http_client.is_closed)

    def test_events_are_forwarded_incrementally_and_connections_close_at_end(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(self.stream.consumed, [])
        content = iter(response.streaming_content)
        self.assertEqual(next(content), self.events[0])
        self.assertEqual(self.stream.consumed, self.events[:1])
        self.assertFalse(self.stream.closed)
        self.assertEqual(list(content), self.events[1:])
        self.assert_connections_closed()

    def test_closing_unread_response_closes_connections_without_reading(self):
        response = self.post()
        self.assertFalse(self.stream.closed)
        response.close()
        self.assertEqual(self.stream.consumed, [])
        self.assert_connections_closed()

    def test_disconnect_after_first_event_closes_connections(self):
        response = self.post()
        content = iter(response.streaming_content)
        self.assertEqual(next(content), self.events[0])
        response.close()
        self.assertEqual(self.stream.consumed, self.events[:1])
        self.assert_connections_closed()

    def test_stream_read_error_propagates_and_closes_connections(self):
        self.stream.chunks = [self.events[0], httpx.ReadError("Connection lost")]
        response = self.post()
        content = iter(response.streaming_content)
        self.assertEqual(next(content), self.events[0])
        with self.assertRaises(httpx.ReadError):
            next(content)
        self.assert_connections_closed()
