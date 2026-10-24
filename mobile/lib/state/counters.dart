import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/oe_api.dart';
import 'realtime.dart';
import 'session.dart';

/// Badge numbers for the tab bar: unread chats, unread notifications, open homework (students).
class Counters extends ChangeNotifier {
  Counters(this.api, this.session, this.realtime) {
    _rt = realtime.events.listen((e) {
      if (e['type'] == 'chat.message' || e['type'] == 'realtime.open') _debounced();
    });
  }

  final OeApi api;
  final Session session;
  final Realtime realtime;
  StreamSubscription<dynamic>? _rt;
  Timer? _timer;
  Timer? _debounce;

  int chats = 0;
  int notifications = 0;
  int homework = 0;

  void start() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 60), (_) => refresh());
    refresh();
  }

  void stop() {
    _timer?.cancel();
    chats = notifications = homework = 0;
    notifyListeners();
  }

  void _debounced() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 600), refresh);
  }

  Future<void> refresh() async {
    if (!session.ready) return;
    try {
      final c = await api.counters();
      chats = (c['chats'] as num?)?.toInt() ?? 0;
      notifications = (c['notifications'] as num?)?.toInt() ?? 0;
      final ch = session.child;
      if (session.isStudent && ch != null && !ch.blocked) {
        final now = DateTime.now();
        homework = (await api.homework(ch.id)).where((h) => h.status == 'assigned' && !h.overdue(now)).length;
      }
      notifyListeners();
    } catch (_) {}
  }

  void setNotificationsRead() {
    notifications = 0;
    notifyListeners();
  }

  @override
  void dispose() {
    _rt?.cancel();
    _timer?.cancel();
    _debounce?.cancel();
    super.dispose();
  }
}
