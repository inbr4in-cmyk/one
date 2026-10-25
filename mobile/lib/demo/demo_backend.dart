import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import '../api/api_client.dart';
import '../config.dart';
import '../util/format.dart' show dateOnly, phonePattern, schoolNow;
import 'fixtures.dart';

typedef _Json = Map<String, dynamic>;

/// The client for the demo build: same [ApiClient], but `data:` URLs (demo uploads) are used as they are.
class DemoApiClient extends ApiClient {
  DemoApiClient({required super.secrets, required DemoBackend backend})
      : super(baseUrl: DemoBackend.base, client: backend.client);

  @override
  String absolute(String url) => url.startsWith('data:') ? url : super.absolute(url);
}

/// An in-memory One English API for the offline demo.
///
/// Serves responses recorded from the real backend ([demoFixturesJson]) for one parent with two children and
/// one student, moves every date forward by the days since the recording, and applies the main actions in
/// memory (messages, homework, ratings, shop orders, consents, complaints, notifications). Nothing leaves
/// the device: the [client] never opens a connection.
class DemoBackend {
  DemoBackend({DateTime Function()? clock}) : _clock = clock ?? DateTime.now {
    final raw = jsonDecode(demoFixturesJson) as _Json;
    final captured = DateTime.parse(raw['captured_at'] as String);
    final now = _clock();
    _shift = DateTime.utc(now.year, now.month, now.day).difference(DateTime.utc(captured.year, captured.month, captured.day));
    for (final role in const ['parent', 'student']) {
      _accounts[role] = _Account(_shiftDates(raw[role]) as _Json);
    }
  }

  static const base = 'https://demo.oneenglish.invalid';
  static const code = '111111';

  final DateTime Function() _clock;
  late final Duration _shift;
  final _accounts = <String, _Account>{};
  int _nextId = 900000;

  late final MockClient client = MockClient(_handle);

  /// The recorded phone numbers, for the «войти как …» buttons.
  String phoneOf(String role) => _accounts[role]!.me['phone'] as String;

  // ---------- plumbing ----------

  static final _isoDate = RegExp(r'^\d{4}-\d{2}-\d{2}$');
  static final _isoDateTime = RegExp(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}');

  Object? _shiftDates(Object? v) {
    if (v is Map) return {for (final e in v.entries) e.key as String: _shiftDates(e.value)};
    if (v is List) return [for (final x in v) _shiftDates(x)];
    if (v is String) {
      if (_isoDateTime.hasMatch(v)) {
        final d = DateTime.tryParse(v);
        if (d != null) return d.toUtc().add(_shift).toIso8601String();
      } else if (_isoDate.hasMatch(v)) {
        final d = DateTime.tryParse('${v}T00:00:00Z');
        if (d != null) {
          final s = d.add(_shift);
          return '${s.year.toString().padLeft(4, '0')}-${s.month.toString().padLeft(2, '0')}-${s.day.toString().padLeft(2, '0')}';
        }
      }
    }
    return v;
  }

  String _nowIso([Duration plus = Duration.zero]) => _clock().toUtc().add(plus).toIso8601String();

  static http.Response _json(Object? data, [int status = 200]) => http.Response.bytes(
        status == 204 ? const <int>[] : utf8.encode(jsonEncode(data)),
        status,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );

  static http.Response _error(int status, String detail) => _json({'detail': detail}, status);

  _Json _tokens(String role) => {
        'access_token': 'demo-access-$role',
        'refresh_token': 'demo-refresh-$role',
        'token_type': 'bearer',
      };

  String _roleForPhone(String phone) {
    final digits = phone.replaceAll(RegExp(r'\D'), '');
    final student = phoneOf('student').replaceAll(RegExp(r'\D'), '');
    return digits == student ? 'student' : 'parent';
  }

  // ---------- requests ----------

  Future<http.Response> _handle(http.Request r) async {
    // A short pause so loaders and buttons behave as they do on a real network.
    await Future<void>.delayed(const Duration(milliseconds: 150));
    final path = r.url.path.replaceFirst(RegExp(r'^.*?/api'), '');
    final q = r.url.queryParameters;
    _Json body = const {};
    final type = r.headers['content-type'] ?? '';
    if (type.contains('json') && r.body.isNotEmpty) {
      final d = jsonDecode(r.body);
      if (d is Map) body = d.cast<String, dynamic>();
    }

    switch ('${r.method} $path') {
      case 'POST /auth/otp/request':
        final p = (body['phone'] as String? ?? '').replaceAll(RegExp(r'\D'), '');
        if (p.length != 11) return _error(422, 'Введите номер полностью: +7 и 10 цифр');
        return _json(null, 204);
      case 'POST /auth/otp/verify':
        if (body['code'] != code) return _error(400, 'Неверный или устаревший код');
        return _json(_tokens(_roleForPhone(body['phone'] as String? ?? '')));
      case 'POST /auth/refresh':
        final t = body['refresh_token'] as String? ?? '';
        final role = t.replaceFirst('demo-refresh-', '');
        if (!t.startsWith('demo-refresh-') || !_accounts.containsKey(role)) return _error(401, 'Сессия истекла');
        return _json(_tokens(role));
    }

    final auth = r.headers['Authorization'] ?? '';
    final role = auth.startsWith('Bearer demo-access-') ? auth.substring('Bearer demo-access-'.length) : null;
    final a = role == null ? null : _accounts[role];
    if (a == null) return _error(401, 'Не авторизован');

    if (r.method == 'GET') return _get(a, path, q);
    if (r.method == 'POST' && path == '/files') return _upload(a, r);
    return _mutate(a, r.method, path, body);
  }

  http.Response _get(_Account a, String path, Map<String, String> q) {
    if (path == '/auth/me') return _json(a.me);
    if (path == '/notifications') {
      final items = a.notices;
      return _json({'unread': items.where((n) => n['read'] != true).length, 'items': items});
    }
    if (path == '/counters') {
      final base = (a.routes['GET /counters']?['body'] as Map?)?.cast<String, dynamic>() ?? {};
      return _json({
        ...base,
        'notifications': a.notices.where((n) => n['read'] != true).length,
        'chats': a.chats.fold<int>(0, (s, c) => s + ((c['unread'] as num?)?.toInt() ?? 0)),
      });
    }
    if (path == '/chats') return _json(a.chats);
    if (path == '/chats/contacts') {
      final list = (a.body('GET /chats/contacts') as List?) ?? const [];
      final term = (q['q'] ?? '').toLowerCase();
      return _json([for (final c in list) if (term.isEmpty || '${(c as Map)['full_name']}'.toLowerCase().contains(term)) c]);
    }
    final m = RegExp(r'^/chats/(\d+)/messages$').firstMatch(path);
    if (m != null) {
      final list = a.messages(int.parse(m.group(1)!));
      if (q['before_id'] != null) return _json(const []);
      final after = int.tryParse(q['after_id'] ?? '');
      return _json(after == null ? list : list.where((x) => (x['id'] as num) > after).toList());
    }
    final s = RegExp(r'^/portal/students/(\d+)/schedule$').firstMatch(path);
    if (s != null) return _json(a.schedule(int.parse(s.group(1)!), q['start'], int.tryParse(q['days'] ?? '') ?? 14));
    if (path == '/shop/orders') return _json(a.orders(int.parse(q['student_id'] ?? '0')));
    for (final p in const ['student_id', 'branch_id', 'group_id']) {
      if (q[p] != null && a.routes.containsKey('GET $path?$p=${q[p]}')) return _recorded(a, 'GET $path?$p=${q[p]}');
    }
    if (a.routes.containsKey('GET $path')) return _recorded(a, 'GET $path');
    if (path.startsWith('/coins/top')) return _json(const []);
    return _error(404, 'Не найдено');
  }

  http.Response _recorded(_Account a, String key) {
    final r = a.routes[key]!;
    return _json(r['body'], (r['status'] as num?)?.toInt() ?? 200);
  }

  http.Response _upload(_Account a, http.Request r) {
    // Parse the single multipart part well enough to hand the file back as a data: URL.
    final bytes = r.bodyBytes;
    final text = latin1.decode(bytes);
    final name = RegExp(r'filename="([^"]*)"').firstMatch(text)?.group(1) ?? 'file';
    final mime = RegExp(r'content-type:\s*([^\r\n]+)', caseSensitive: false).allMatches(text).lastOrNull?.group(1)?.trim() ??
        'application/octet-stream';
    final start = text.indexOf('\r\n\r\n', text.indexOf('filename=')) + 4;
    final end = text.lastIndexOf('\r\n--');
    final data = Uint8List.sublistView(bytes, start, end > start ? end : bytes.length);
    final key = 'demo-${_nextId++}';
    final url = 'data:$mime;base64,${base64Encode(data)}';
    a.uploads[key] = url;
    return _json({'key': key, 'url': url, 'name': latin1Decode(name), 'size': data.length});
  }

  static String latin1Decode(String s) {
    try {
      return utf8.decode(latin1.encode(s));
    } catch (_) {
      return s;
    }
  }

  http.Response _mutate(_Account a, String method, String path, _Json body) {
    final me = a.me;
    Match? m;
    if (path == '/auth/logout' || path.startsWith('/auth/devices') || path.startsWith('/auth/sessions')) {
      return _json(null, 204);
    }
    if (path == '/ws/ticket') return _json({'ticket': 'demo'});
    if (path == '/notifications/read-all') {
      for (final n in a.notices) {
        n['read'] = true;
      }
      return _json({'ok': true});
    }

    // ---- chats ----
    if ((m = RegExp(r'^/chats/(\d+)/messages$').firstMatch(path)) != null) {
      final chatId = int.parse(m!.group(1)!);
      final text = (body['text'] as String?)?.trim();
      if (a.isStudent && text != null && phonePattern.hasMatch(text)) {
        return _error(400, 'Ученики не отправляют номера телефонов в чатах (правила школы)');
      }
      final kind = body['kind'] as String? ?? 'text';
      final msg = <String, dynamic>{
        'id': _nextId++,
        'chat_id': chatId,
        'sender_id': me['id'],
        'sender_name': me['full_name'],
        'sender_kind': me['kind'],
        'sender_position': null,
        'at': _nowIso(),
        'kind': kind,
        'text': text,
        'file_url': a.uploads[body['file_key']],
        'file_name': body['file_name'],
        'pinned': false,
        'edited': false,
        'hidden': false,
      };
      a.messages(chatId).add(msg);
      final chat = a.chats.where((c) => c['id'] == chatId).firstOrNull;
      if (chat != null) {
        chat['last_message'] = {
          'text': text ?? (kind == 'voice' ? 'Голосовое сообщение' : body['file_name'] ?? 'Файл'),
          'at': msg['at'],
          'sender': me['full_name'],
        };
        a.chats
          ..remove(chat)
          ..insert(0, chat);
      }
      return _json(msg, 201);
    }
    if ((m = RegExp(r'^/chats/(\d+)/read$').firstMatch(path)) != null) {
      for (final c in a.chats.where((c) => c['id'] == int.parse(m!.group(1)!))) {
        c['unread'] = 0;
      }
      return _json({'ok': true});
    }
    if (path == '/chats/direct') {
      final uid = (body['user_id'] as num).toInt();
      final existing = a.chats.where((c) => (c['other_user'] as Map?)?['id'] == uid).firstOrNull;
      if (existing != null) return _json(existing);
      final contact = ((a.body('GET /chats/contacts') as List?) ?? const []).cast<Map>().where((c) => c['id'] == uid).firstOrNull;
      if (contact == null) return _error(403, 'Написать этому сотруднику нельзя');
      final chat = <String, dynamic>{
        'id': _nextId++,
        'kind': 'direct',
        'title': contact['full_name'],
        'group_id': null,
        'unread': 0,
        'last_message': null,
        'other_user': {'id': uid, 'full_name': contact['full_name'], 'kind': 'staff', 'position': contact['position']},
        'members': 2,
        'about_student_id': null,
      };
      a.chats.insert(0, chat);
      a.routes['GET /chats/${chat['id']}/pinned'] = {'status': 200, 'body': <Object>[]};
      return _json(chat, 201);
    }
    if ((m = RegExp(r'^/chat-messages/(\d+)$').firstMatch(path)) != null && method == 'DELETE') {
      final id = int.parse(m!.group(1)!);
      for (final list in a.messageLists) {
        for (final x in list.where((x) => x['id'] == id)) {
          x['hidden'] = true;
        }
      }
      return _json(null, 204);
    }

    // ---- study ----
    if ((m = RegExp(r'^/portal/homework/(\d+)/submit$').firstMatch(path)) != null) {
      final id = int.parse(m!.group(1)!);
      final list = a.body('GET /portal/students/${body['student_id']}/homework') as List?;
      final hw = list?.cast<Map>().where((h) => h['id'] == id).firstOrNull;
      if (hw == null) return _error(404, 'Задание не найдено');
      hw['status'] = 'submitted';
      hw['answer'] = body['answer'];
      hw['file_url'] = a.uploads[body['file_key']];
      return _json({'ok': true});
    }
    if ((m = RegExp(r'^/portal/lessons/(\d+)/rate$').firstMatch(path)) != null) {
      final id = int.parse(m!.group(1)!);
      final att = a.body('GET /portal/students/${body['student_id']}/attendance') as Map?;
      for (final x in ((att?['items'] as List?) ?? const []).cast<Map>().where((x) => x['lesson_id'] == id)) {
        x['my_rating'] = body['stars'];
      }
      return _json({'ok': true});
    }

    // ---- coins & shop ----
    if (path == '/shop/orders' && method == 'POST') {
      final sid = (body['student_id'] as num).toInt();
      final child = a.child(sid);
      final item = a.shopItems(child?['branch']?['id']).where((i) => i['id'] == body['item_id']).firstOrNull;
      if (item == null) return _error(404, 'Товар не найден');
      final price = (item['price_coins'] as num).toInt();
      final coins = a.coins(sid);
      final bal = (coins['balance'] as num).toInt();
      if ((item['stock'] as num? ?? 1) <= 0) return _error(409, 'Товар закончился');
      if (bal < price) return _error(409, 'Не хватает ${price - bal} коинов');
      item['stock'] = (item['stock'] as num? ?? 1) - 1;
      final order = {'id': _nextId++, 'item': item['name'], 'item_id': item['id'], 'coins': price, 'status': 'placed', 'created_at': _nowIso(), 'issued_at': null};
      a.orders(sid).insert(0, order);
      a.addCoins(sid, -price, 'order_hold', item['name'] as String, _nowIso());
      return _json({'id': order['id'], 'status': 'placed', 'balance': bal - price}, 201);
    }
    if ((m = RegExp(r'^/shop/orders/(\d+)/status$').firstMatch(path)) != null) {
      final id = int.parse(m!.group(1)!);
      for (final e in a.ordersBy.entries) {
        final o = e.value.where((o) => o['id'] == id).firstOrNull;
        if (o == null) continue;
        if (o['status'] != 'placed') return _error(409, 'Заказ уже нельзя отменить');
        o['status'] = 'cancelled';
        a.addCoins(e.key, (o['coins'] as num).toInt(), 'order_release', 'Заказ отменён', _nowIso());
        return _json(o);
      }
      return _error(404, 'Заказ не найден');
    }

    // ---- compliance ----
    if (path == '/consents' && method == 'POST') {
      final docId = (body['document_id'] as num).toInt();
      final doc = [a.body('GET /documents/rules'), a.body('GET /documents/recording')]
          .whereType<Map>()
          .where((d) => d['id'] == docId)
          .firstOrNull;
      if (doc == null) return _error(404, 'Документ не найден');
      final consent = {
        'id': _nextId++,
        'document_id': docId,
        'kind': doc['kind'],
        'version': doc['version'],
        'student_id': body['student_id'],
        'accepted_at': _nowIso(),
        'revoked_at': null,
      };
      a.consents.add(consent);
      if (doc['kind'] == 'rules') me['rules_accepted_version'] = doc['version'];
      return _json({'id': consent['id'], 'version': doc['version']}, 201);
    }
    if ((m = RegExp(r'^/consents/(\d+)/revoke$').firstMatch(path)) != null) {
      for (final c in a.consents.where((c) => c['id'] == int.parse(m!.group(1)!))) {
        c['revoked_at'] = _nowIso();
      }
      return _json({'ok': true});
    }
    if (path == '/complaints' && method == 'POST') {
      final c = {
        'id': _nextId++,
        'subject': body['subject'],
        'body': body['body'],
        'against_user_id': body['against_user_id'],
        'status': 'new',
        'created_at': _nowIso(),
        'due_at': _nowIso(const Duration(days: 3)),
        'answer': null,
        'answered_at': null,
      };
      a.complaints.insert(0, c);
      return _json(c, 201);
    }
    if ((m = RegExp(r'^/complaints/(\d+)$').firstMatch(path)) != null) {
      final c = a.complaints.where((c) => c['id'] == int.parse(m!.group(1)!)).firstOrNull;
      if (c == null) return _error(404, 'Обращение не найдено');
      c['status'] = 'appealed';
      return _json(c);
    }
    return _error(404, 'В демо-версии это действие недоступно');
  }
}

/// One recorded account and its in-memory state.
class _Account {
  _Account(_Json data)
      : me = (data['me'] as Map).cast<String, dynamic>(),
        routes = {for (final e in (data['routes'] as Map).entries) e.key as String: (e.value as Map).cast<String, dynamic>()};

  final _Json me;
  final Map<String, _Json> routes;
  final uploads = <Object?, String>{};
  final ordersBy = <int, List<_Json>>{};

  bool get isStudent => me['kind'] == 'student';

  Object? body(String key) => routes[key]?['body'];

  List<_Json> _list(String key) {
    final r = routes.putIfAbsent(key, () => {'status': 200, 'body': <Object>[]});
    final b = r['body'];
    if (b is List<_Json>) return b;
    final list = [for (final x in (b as List? ?? const [])) (x as Map).cast<String, dynamic>()];
    r['body'] = list;
    return list;
  }

  List<_Json> get chats => _list('GET /chats');
  List<_Json> messages(int chatId) => _list('GET /chats/$chatId/messages');
  Iterable<List<_Json>> get messageLists => routes.keys.where((k) => RegExp(r'^GET /chats/\d+/messages$').hasMatch(k)).map(_list);
  List<_Json> get consents => _list('GET /consents/my');
  List<_Json> get complaints => _list('GET /complaints/my');

  List<_Json> get notices {
    final n = (routes['GET /notifications']?['body'] as Map?)?.cast<String, dynamic>() ?? {'items': <Object>[]};
    routes['GET /notifications'] = {'status': 200, 'body': n};
    final items = n['items'];
    if (items is List<_Json>) return items;
    final list = [for (final x in (items as List? ?? const [])) (x as Map).cast<String, dynamic>()];
    n['items'] = list;
    return list;
  }

  _Json? child(int id) => ((body('GET /portal/me') as Map?)?['children'] as List?)?.cast<Map>().where((c) => c['id'] == id).firstOrNull?.cast<String, dynamic>();

  List<_Json> shopItems(Object? branchId) => _list('GET /shop/items?branch_id=$branchId');

  List<_Json> orders(int sid) => ordersBy.putIfAbsent(sid, () => _list('GET /shop/orders?student_id=$sid'));

  _Json coins(int sid) {
    final r = routes.putIfAbsent('GET /students/$sid/coins', () => {'status': 200, 'body': {'balance': 0, 'items': <Object>[]}});
    final b = (r['body'] as Map).cast<String, dynamic>();
    b['items'] = [for (final x in (b['items'] as List? ?? const [])) (x as Map).cast<String, dynamic>()];
    r['body'] = b;
    return b;
  }

  void addCoins(int sid, int delta, String kind, String reason, String at) {
    final c = coins(sid);
    c['balance'] = (c['balance'] as num).toInt() + delta;
    (c['items'] as List).insert(0, {'at': at, 'kind': kind, 'delta': delta, 'reason': reason});
    final ch = ((body('GET /portal/me') as Map?)?['children'] as List?)?.cast<Map>().where((x) => x['id'] == sid).firstOrNull;
    if (ch != null) ch['coins'] = c['balance'];
  }

  /// Lessons from both recorded windows that fall in [start, start + days) on the school's calendar.
  List<Object?> schedule(int sid, String? start, int days) {
    final all = <String, Object?>{};
    for (final k in ['GET /portal/students/$sid/schedule#1', 'GET /portal/students/$sid/schedule#2']) {
      for (final l in (body(k) as List? ?? const [])) {
        all['${(l as Map)['id']}'] = l;
      }
    }
    final from = start == null ? dateOnly(schoolNow()) : DateTime.utc(int.parse(start.substring(0, 4)), int.parse(start.substring(5, 7)), int.parse(start.substring(8, 10)));
    final to = from.add(Duration(days: days));
    final list = all.values.where((l) {
      final at = DateTime.tryParse('${(l as Map)['starts_at']}');
      if (at == null) return false;
      final local = at.toUtc().add(AppConfig.schoolUtcOffset);
      final d = DateTime.utc(local.year, local.month, local.day);
      return !d.isBefore(from) && d.isBefore(to);
    }).toList()
      ..sort((a, b) => '${(a as Map)['starts_at']}'.compareTo('${(b as Map)['starts_at']}'));
    return list;
  }
}
