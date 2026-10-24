import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// A small in-memory stand-in for the One English API, enough for widget and session tests.
class FakeBackend {
  FakeBackend({this.kind = 'parent', this.rulesAccepted = '1.0', this.rulesVersion = '1.0', this.blocked = false});

  String kind;
  String? rulesAccepted;
  String? rulesVersion;
  bool blocked;
  String access = 'a1';
  String refresh = 'r1';
  int refreshCalls = 0;
  final List<http.BaseRequest> requests = [];
  final List<Map<String, dynamic>> bodies = [];
  final Map<String, Object? Function(http.Request)> overrides = {};

  late final MockClient client = MockClient(_handle);

  Map<String, dynamic> _child(int id, String name) => {
        'id': id,
        'full_name': name,
        'status': 'active',
        'branch': {'id': 1, 'name': 'Самал', 'phone': '+77001002018'},
        'level': 'Pre-Intermediate',
        'lessons_left': blocked ? 0 : 5,
        'money_balance': 0,
        'debt': blocked,
        'blocked': blocked,
        'stars': 3,
        'coins': 120,
        'groups': [
          {'id': 10, 'name': 'PI-3', 'level': 'Pre-Intermediate', 'teacher': 'Айгерим Нурланова', 'teacher_id': 50, 'chat_id': 7}
        ],
      };

  Future<http.Response> _handle(http.Request r) async {
    requests.add(r);
    Map<String, dynamic> body = {};
    if (r.body.isNotEmpty) {
      try {
        body = (jsonDecode(r.body) as Map).cast<String, dynamic>();
      } catch (_) {}
    }
    bodies.add(body);
    final path = r.url.path.replaceFirst('/api', '');
    final key = '${r.method} $path';
    if (overrides.containsKey(key)) return _json(overrides[key]!(r));

    if (key == 'POST /auth/refresh') {
      refreshCalls++;
      if (body['refresh_token'] != refresh) return _json({'detail': 'Сессия истекла'}, 401);
      access = 'a${refreshCalls + 1}';
      refresh = 'r${refreshCalls + 1}';
      return _json({'access_token': access, 'refresh_token': refresh});
    }
    if (key == 'POST /auth/otp/request') return _json({'sent': true});
    if (key == 'POST /auth/otp/verify') {
      if (body['code'] != '123456') return _json({'detail': 'Неверный код'}, 400);
      return _json({'access_token': access, 'refresh_token': refresh});
    }
    if (r.headers['Authorization'] != 'Bearer $access') return _json({'detail': 'Не авторизован'}, 401);
    switch (key) {
      case 'GET /auth/me':
        return _json({
          'id': 1,
          'kind': kind,
          'full_name': kind == 'parent' ? 'Гульнара Ахметова' : 'Арман Ахметов',
          'phone': '+77052000001',
          'locale': 'ru',
          'rules_accepted_version': rulesAccepted,
        });
      case 'GET /portal/me':
        return _json({
          'kind': kind,
          'full_name': 'x',
          'children': kind == 'parent'
              ? [_child(3, 'Арман Ахметов'), _child(4, 'Алия Ахметова')]
              : [_child(3, 'Арман Ахметов')],
        });
      case 'GET /documents/rules':
        if (rulesVersion == null) return _json({'detail': 'Не опубликовано'}, 404);
        return _json({'id': 9, 'kind': 'rules', 'version': rulesVersion, 'title': 'Правила школы', 'body': '# Общее\n\nБудьте вежливы.'});
      case 'POST /consents':
        rulesAccepted = rulesVersion;
        return _json({'id': 1, 'version': rulesVersion});
      case 'POST /auth/logout':
        return _json(null, 204);
    }
    if (r.method == 'GET' && (path.endsWith('/schedule') || path.endsWith('/homework') || path == '/chats' || path.endsWith('/my'))) {
      return _json([]);
    }
    if (path == '/notifications') return _json({'unread': 0, 'items': []});
    if (path == '/counters') return _json({'chats_unread': 0, 'notifications_unread': 0});
    return _json({'detail': 'Не найдено'}, 404);
  }

  static http.Response _json(Object? data, [int status = 200]) => http.Response.bytes(
        status == 204 ? const [] : utf8.encode(jsonEncode(data)),
        status,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
}
