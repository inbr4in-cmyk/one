import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'secret_store.dart';

/// An error the server explained: [detail] is its `detail` text and is shown to the user as is.
class ApiException implements Exception {
  ApiException(this.status, this.detail);
  final int status;
  final String detail;

  bool get isNetwork => status == 0;

  @override
  String toString() => 'ApiException($status, $detail)';
}

/// HTTP client for the One English API v1 (same API as the web cabinet).
///
/// * Every request carries `X-Client: mobile`, so the server returns the refresh token in the body.
/// * The access token lives in memory only; the refresh token is kept in [SecretStore].
/// * On 401 the client refreshes once and retries; concurrent requests share one refresh.
/// * When the session can't be restored, [onAuthLost] fires (the app returns to the login screen).
class ApiClient {
  ApiClient({required String baseUrl, required this.secrets, http.Client? client})
      : base = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl,
        _http = client ?? http.Client();

  static const refreshKey = 'oe.refresh';
  static const _headers = {'X-Client': 'mobile', 'Accept': 'application/json'};

  final String base;
  final SecretStore secrets;
  final http.Client _http;
  String? _access;
  Future<bool>? _refreshing;

  /// Called once when a refresh fails: tokens are already cleared.
  void Function()? onAuthLost;

  bool get hasAccess => _access != null;
  String? get accessToken => _access;

  Uri uri(String path) => Uri.parse('$base/api$path');

  /// Absolute URL for a server path such as a signed `/api/files/…` link.
  String absolute(String url) => url.startsWith('http') ? url : '$base${url.startsWith('/') ? '' : '/'}$url';

  /// `wss://host/api/ws?ticket=…` for the realtime socket.
  Uri wsUri(String ticket) {
    final u = Uri.parse(base);
    return u.replace(
      scheme: u.scheme == 'https' ? 'wss' : 'ws',
      path: '${u.path}/api/ws',
      queryParameters: {'ticket': ticket},
    );
  }

  // ---------- session ----------

  /// Store a token pair from /auth/otp/verify or /auth/refresh.
  Future<void> setTokens(String access, String? refresh) async {
    _access = access;
    if (refresh != null) await secrets.write(refreshKey, refresh);
  }

  Future<void> clearTokens() async {
    _access = null;
    await secrets.write(refreshKey, null);
  }

  /// Whether a refresh token is stored (a previous session may be restorable).
  Future<bool> hasStoredSession() async => (await secrets.read(refreshKey)) != null;

  /// Exchange the stored refresh token for a new pair. Only one refresh runs at a time.
  Future<bool> refresh() {
    return _refreshing ??= _doRefresh().whenComplete(() => _refreshing = null);
  }

  Future<bool> _doRefresh() async {
    final token = await secrets.read(refreshKey);
    if (token == null) return false;
    http.Response res;
    try {
      res = await _http.post(uri('/auth/refresh'),
          headers: {..._headers, 'Content-Type': 'application/json'}, body: jsonEncode({'refresh_token': token}));
    } catch (_) {
      // Offline: keep the stored token, the caller sees a network error.
      throw ApiException(0, '');
    }
    if (res.statusCode == 200) {
      final data = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
      final access = data['access_token'] as String?;
      if (access == null) return false;
      await setTokens(access, data['refresh_token'] as String?);
      return true;
    }
    if (res.statusCode == 401 || res.statusCode == 403) {
      await clearTokens();
      return false;
    }
    throw ApiException(res.statusCode, _detail(res));
  }

  // ---------- requests ----------

  Future<dynamic> get(String path, {Map<String, Object?>? query}) => _request('GET', path, query: query);
  Future<dynamic> post(String path, [Object? body]) => _request('POST', path, body: body);
  Future<dynamic> delete(String path) => _request('DELETE', path);

  /// Requests that must not trigger a refresh (login).
  Future<dynamic> postPublic(String path, Object? body) => _request('POST', path, body: body, auth: false);

  Future<dynamic> _request(String method, String path,
      {Object? body, Map<String, Object?>? query, bool auth = true}) async {
    var u = uri(path);
    if (query != null) {
      final q = <String, String>{
        for (final e in query.entries)
          if (e.value != null && e.value != '') e.key: '${e.value}',
      };
      if (q.isNotEmpty) u = u.replace(queryParameters: q);
    }
    Future<http.Response> send() {
      final req = http.Request(method, u)..headers.addAll(_headers);
      if (auth && _access != null) req.headers['Authorization'] = 'Bearer $_access';
      if (body != null) {
        req.headers['Content-Type'] = 'application/json';
        req.body = jsonEncode(body);
      }
      return _http.send(req).then(http.Response.fromStream);
    }

    http.Response res;
    try {
      if (auth && _access == null && await hasStoredSession()) await refresh();
      res = await send();
      if (res.statusCode == 401 && auth) {
        final ok = await refresh();
        if (!ok) {
          _lost();
          throw ApiException(401, _detail(res));
        }
        res = await send();
        if (res.statusCode == 401) {
          await clearTokens();
          _lost();
        }
      }
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException(0, '');
    }
    return _decode(res);
  }

  /// Upload a file through POST /api/files; returns `{key, url, name, size}`.
  Future<Map<String, dynamic>> upload(Uint8List bytes, String filename, String contentType) async {
    Future<http.Response> send() {
      final req = http.MultipartRequest('POST', uri('/files'))..headers.addAll(_headers);
      if (_access != null) req.headers['Authorization'] = 'Bearer $_access';
      req.files.add(http.MultipartFile.fromBytes('file', bytes,
          filename: filename, contentType: MediaType.parse(contentType)));
      return _http.send(req).then(http.Response.fromStream);
    }

    http.Response res;
    try {
      res = await send();
      if (res.statusCode == 401) {
        if (!await refresh()) {
          _lost();
          throw ApiException(401, '');
        }
        res = await send();
      }
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException(0, '');
    }
    return (await _decode(res)) as Map<String, dynamic>;
  }

  void _lost() => onAuthLost?.call();

  dynamic _decode(http.Response res) {
    if (res.statusCode >= 200 && res.statusCode < 300) {
      if (res.statusCode == 204 || res.bodyBytes.isEmpty) return null;
      return jsonDecode(utf8.decode(res.bodyBytes));
    }
    throw ApiException(res.statusCode, _detail(res));
  }

  /// FastAPI sends `detail` as a string or as a list of validation errors.
  static String _detail(http.Response res) {
    try {
      final data = jsonDecode(utf8.decode(res.bodyBytes));
      if (data is Map && data['detail'] != null) {
        final d = data['detail'];
        if (d is String) return d;
        if (d is List && d.isNotEmpty && d.first is Map && d.first['msg'] is String) return d.first['msg'] as String;
      }
    } catch (_) {}
    return '';
  }
}
