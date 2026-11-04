import 'package:flutter_test/flutter_test.dart';
import 'package:one_english/api/api_client.dart';
import 'package:one_english/api/oe_api.dart';
import 'package:one_english/api/secret_store.dart';
import 'package:one_english/demo/demo_backend.dart';

OeApi _api(DemoBackend b) => OeApi(DemoApiClient(secrets: MemorySecretStore(), backend: b));

void main() {
  test('demo: parent signs in with 111111 and sees two children and their schedule', () async {
    final b = DemoBackend();
    final api = _api(b);
    final phone = b.phoneOf('parent');
    await api.otpRequest(phone);
    await expectLater(api.otpVerify(phone, '000000'), throwsA(isA<ApiException>()));
    await api.otpVerify(phone, DemoBackend.code);
    expect(await api.client.secrets.read(ApiClient.deviceKey), 'demo-device');
    final me = await api.portalMe();
    expect(me.children, hasLength(2));
    final lessons = await api.schedule(me.children.first.id, days: 14);
    expect(lessons, isNotEmpty);
  });

  test('demo: any other phone opens the parent account', () async {
    final b = DemoBackend();
    final api = _api(b);
    await api.otpVerify('+77000000000', DemoBackend.code);
    expect((await api.authMe()).phone, b.phoneOf('parent'));
  });

  test('demo: student chat, phone rule and shop order work in memory', () async {
    final b = DemoBackend();
    final api = _api(b);
    await api.otpVerify(b.phoneOf('student'), DemoBackend.code);
    final me = await api.portalMe();
    final sid = me.children.first.id;

    final chat = (await api.chats()).last;
    final before = (await api.messages(chat.id)).length;
    await api.send(chat.id, text: 'Hello from the demo');
    expect((await api.messages(chat.id)).length, before + 1);
    expect((await api.chats()).first.id, chat.id);
    await expectLater(
        api.send(chat.id, text: 'мой номер +7 705 100 00 13'),
        throwsA(isA<ApiException>().having((e) => e.status, 'status', 400)));

    final balance = (await api.coins(sid)).balance;
    final item = (await api.shopItems(me.children.first.branch.id)).firstWhere((i) => i.priceCoins <= balance);
    expect(await api.order(sid, item.id), balance - item.priceCoins);
    final order = (await api.orders(sid)).first;
    await api.cancelOrder(order.id);
    expect((await api.coins(sid)).balance, balance);
  });
}
