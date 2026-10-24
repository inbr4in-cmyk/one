import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:one_english/api/api_client.dart';
import 'package:one_english/api/secret_store.dart';

import 'support/fake_backend.dart';

void main() {
  late FakeBackend be;
  late MemorySecretStore store;
  late ApiClient api;

  setUp(() {
    be = FakeBackend();
    store = MemorySecretStore();
    api = ApiClient(baseUrl: 'https://oe.test/', secrets: store, client: be.client);
  });

  test('every request carries X-Client: mobile', () async {
    await api.postPublic('/auth/otp/request', {'phone': '+77011234567'});
    expect(be.requests.single.headers['X-Client'], 'mobile');
    expect(be.requests.single.url.toString(), 'https://oe.test/api/auth/otp/request');
  });

  test('refresh sends the stored token in the body and keeps the new pair', () async {
    await store.write(ApiClient.refreshKey, 'r1');
    expect(await api.refresh(), isTrue);
    expect(be.bodies.single, {'refresh_token': 'r1'});
    expect(be.requests.single.headers['X-Client'], 'mobile');
    expect(api.accessToken, 'a2');
    expect(await store.read(ApiClient.refreshKey), 'r2');
  });

  test('a stale access token is refreshed once and the request retried', () async {
    await api.setTokens('old', 'r1');
    final me = await api.get('/auth/me') as Map;
    expect(me['kind'], 'parent');
    expect(be.refreshCalls, 1);
    expect(be.requests.map((r) => r.url.path), ['/api/auth/me', '/api/auth/refresh', '/api/auth/me']);
  });

  test('concurrent 401s share a single refresh', () async {
    await api.setTokens('old', 'r1');
    final results = await Future.wait([api.get('/auth/me'), api.get('/portal/me'), api.get('/documents/rules')]);
    expect(results, hasLength(3));
    expect(be.refreshCalls, 1);
  });

  test('a failed refresh clears the tokens and reports the lost session', () async {
    await api.setTokens('old', 'wrong');
    var lost = 0;
    api.onAuthLost = () => lost++;
    await expectLater(api.get('/auth/me'), throwsA(isA<ApiException>().having((e) => e.status, 'status', 401)));
    expect(lost, 1);
    expect(api.hasAccess, isFalse);
    expect(await store.read(ApiClient.refreshKey), isNull);
  });

  test('on a cold start the stored refresh token is used before the first request', () async {
    await store.write(ApiClient.refreshKey, 'r1');
    await api.get('/auth/me');
    expect(be.requests.first.url.path, '/api/auth/refresh');
  });

  test('server detail is surfaced as is (string and validation list)', () async {
    final c = ApiClient(
      baseUrl: 'https://oe.test',
      secrets: store,
      client: MockClient((r) async => r.url.path.endsWith('/a')
          ? http.Response.bytes(utf8.encode(jsonEncode({'detail': 'Доступ приостановлен до оплаты'})), 403)
          : http.Response.bytes(
              utf8.encode(jsonEncode({
                'detail': [
                  {'msg': 'Поле обязательно', 'loc': ['body', 'phone']}
                ]
              })),
              422)),
    );
    await expectLater(c.postPublic('/a', {}),
        throwsA(isA<ApiException>().having((e) => e.detail, 'detail', 'Доступ приостановлен до оплаты')));
    await expectLater(c.postPublic('/b', {}), throwsA(isA<ApiException>().having((e) => e.detail, 'detail', 'Поле обязательно')));
  });

  test('network failures become status 0', () async {
    final c = ApiClient(baseUrl: 'https://oe.test', secrets: store, client: MockClient((_) => throw http.ClientException('down')));
    await expectLater(c.postPublic('/auth/otp/request', {}), throwsA(isA<ApiException>().having((e) => e.isNetwork, 'net', true)));
  });

  test('upload is multipart with field "file" and the given content type', () async {
    late http.MultipartRequest seen;
    final c = ApiClient(
        baseUrl: 'https://oe.test',
        secrets: store,
        client: MockClient.streaming((r, body) async {
          seen = r as http.MultipartRequest;
          final payload = await body.toBytes();
          expect(utf8.decode(payload, allowMalformed: true), contains('filename="voice.m4a"'));
          return http.StreamedResponse(Stream.value(utf8.encode('{"key":"k1","url":"/api/files/k1","name":"voice.m4a","size":3}')), 200);
        }));
    await c.setTokens('tok', null);
    final r = await c.upload(Uint8List.fromList([1, 2, 3]), 'voice.m4a', 'audio/mp4');
    expect(r['key'], 'k1');
    expect(seen.headers['Authorization'], 'Bearer tok');
    expect(seen.headers['X-Client'], 'mobile');
    expect(seen.files.single.field, 'file');
    expect(seen.files.single.contentType.mimeType, 'audio/mp4');
  });

  test('websocket and file URLs', () {
    expect(api.wsUri('T 1').toString(), 'wss://oe.test/api/ws?ticket=T+1');
    expect(ApiClient(baseUrl: 'http://localhost:8000', secrets: store).wsUri('x').toString(), 'ws://localhost:8000/api/ws?ticket=x');
    expect(api.absolute('/api/files/k?exp=1&sig=s'), 'https://oe.test/api/files/k?exp=1&sig=s');
    expect(api.absolute('https://cdn/x.png'), 'https://cdn/x.png');
  });
}
