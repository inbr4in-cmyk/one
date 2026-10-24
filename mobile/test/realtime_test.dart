import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:one_english/api/api_client.dart';
import 'package:one_english/api/oe_api.dart';
import 'package:one_english/api/secret_store.dart';
import 'package:one_english/state/realtime.dart';
import 'package:stream_channel/stream_channel.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'support/fake_backend.dart';

class _Sink implements WebSocketSink {
  _Sink(this.sent);
  final List<Object?> sent;
  @override
  void add(Object? data) => sent.add(data);
  @override
  Future<void> close([int? closeCode, String? closeReason]) async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FakeSocket with StreamChannelMixin<dynamic> implements WebSocketChannel {
  FakeSocket(this.uri);
  final Uri uri;
  final incoming = StreamController<dynamic>();
  final sent = <Object?>[];
  int? code;

  void closeWith(int c) {
    code = c;
    incoming.close();
  }

  @override
  Stream<dynamic> get stream => incoming.stream;
  @override
  WebSocketSink get sink => _Sink(sent);
  @override
  Future<void> get ready => Future.value();
  @override
  int? get closeCode => code;
  @override
  String? get closeReason => null;
  @override
  String? get protocol => null;
}

void main() {
  late FakeBackend be;
  late OeApi api;
  final sockets = <FakeSocket>[];

  setUp(() async {
    sockets.clear();
    be = FakeBackend();
    var n = 0;
    be.overrides['POST /ws/ticket'] = (_) => {'ticket': 't${++n}'};
    final client = ApiClient(baseUrl: 'https://oe.test', secrets: MemorySecretStore(), client: be.client);
    await client.setTokens('a1', 'r1');
    api = OeApi(client);
  });

  Realtime make({Duration ping = const Duration(seconds: 25)}) => Realtime(api, pingEvery: ping, connect: (u) {
        final s = FakeSocket(u);
        sockets.add(s);
        return s;
      });

  test('opens with a ticket, forwards events, drops pongs, pings', () async {
    final rt = make(ping: const Duration(milliseconds: 20));
    final events = <String>[];
    rt.events.listen((e) => events.add(e['type'] as String));
    rt.start();
    await pumpEventQueue();
    expect(sockets.single.uri.toString(), 'wss://oe.test/api/ws?ticket=t1');
    sockets.single.incoming.add('{"type":"pong"}');
    sockets.single.incoming.add('{"type":"chat.message","chat_id":7,"message":{"id":1}}');
    sockets.single.incoming.add('not json');
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(events, ['realtime.open', 'chat.message']);
    expect(sockets.single.sent, contains('ping'));
    rt.dispose();
  });

  test('close code 4401 ends the session and does not reconnect', () async {
    final rt = make();
    var lost = 0;
    rt.onSessionLost = () => lost++;
    rt.start();
    await pumpEventQueue();
    sockets.single.closeWith(4401);
    await pumpEventQueue();
    expect(lost, 1);
    expect(rt.connected, isFalse);
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    expect(sockets, hasLength(1));
    rt.dispose();
  });

  test('other drops reconnect with a fresh ticket', () async {
    final rt = make();
    rt.start();
    await pumpEventQueue();
    sockets.single.closeWith(1006);
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    expect(sockets, hasLength(2));
    expect(sockets.last.uri.queryParameters['ticket'], 't2');
    rt.dispose();
  });
}
