import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../api/oe_api.dart';

typedef SocketFactory = WebSocketChannel Function(Uri uri);

/// One realtime socket per signed-in app: POST /api/ws/ticket, then `wss …/api/ws?ticket=…`.
/// Pings every 25 s; close code 4401 means the session ended (→ sign out); other drops reconnect with backoff.
class Realtime {
  Realtime(this.api, {SocketFactory? connect, this.pingEvery = const Duration(seconds: 25)})
      : _connect = connect ?? WebSocketChannel.connect;

  final OeApi api;
  final SocketFactory _connect;
  final Duration pingEvery;
  final _events = StreamController<Map<String, dynamic>>.broadcast();
  WebSocketChannel? _ch;
  StreamSubscription<dynamic>? _sub;
  Timer? _ping;
  Timer? _retry;
  int _attempt = 0;
  bool _running = false;

  /// Called on close code 4401.
  void Function()? onSessionLost;

  Stream<Map<String, dynamic>> get events => _events.stream;
  Stream<Map<String, dynamic>> on(String type) => events.where((e) => e['type'] == type);
  bool get connected => _ch != null;

  void start() {
    if (_running) return;
    _running = true;
    _attempt = 0;
    _open();
  }

  void stop() {
    _running = false;
    _retry?.cancel();
    _ping?.cancel();
    _sub?.cancel();
    _ch?.sink.close();
    _ch = null;
  }

  /// App returned to the foreground or the network came back: connect now.
  void wake() {
    if (_running && _ch == null) {
      _retry?.cancel();
      _attempt = 0;
      _open();
    }
  }

  Future<void> _open() async {
    if (!_running || _ch != null) return;
    String ticket;
    try {
      ticket = await api.wsTicket();
    } catch (_) {
      _schedule();
      return;
    }
    if (!_running) return;
    final ch = _connect(api.client.wsUri(ticket));
    _ch = ch;
    try {
      await ch.ready;
    } catch (_) {
      _ch = null;
      _schedule();
      return;
    }
    _attempt = 0;
    _events.add({'type': 'realtime.open'});
    _ping?.cancel();
    _ping = Timer.periodic(pingEvery, (_) => _ch?.sink.add('ping'));
    _sub = ch.stream.listen((m) {
      try {
        final data = jsonDecode('$m');
        if (data is Map<String, dynamic> && data['type'] is String && data['type'] != 'pong') _events.add(data);
      } catch (_) {}
    }, onDone: () => _closed(ch), onError: (_) => _closed(ch));
  }

  void _closed(WebSocketChannel ch) {
    if (_ch != ch) return;
    _ch = null;
    _ping?.cancel();
    if (ch.closeCode == 4401) {
      stop();
      onSessionLost?.call();
      return;
    }
    _schedule();
  }

  void _schedule() {
    if (!_running) return;
    _retry?.cancel();
    final base = min(30000, 1000 * pow(2, _attempt).toInt());
    _attempt++;
    _retry = Timer(Duration(milliseconds: (base * (0.5 + Random().nextDouble() / 2)).round()), _open);
  }

  void dispose() {
    stop();
    _events.close();
  }
}
