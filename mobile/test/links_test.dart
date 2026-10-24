import 'package:flutter_test/flutter_test.dart';
import 'package:one_english/push/links.dart';

void main() {
  test('server links map onto app routes', () {
    final cases = {
      null: '/home',
      '': '/home',
      '/portal/coins': '/coins',
      '/portal/shop': '/coins',
      '/portal/children/12': '/home?child=12',
      '/chats/5': '/chats/5',
      '/chats?chat=8': '/chats/8',
      '/chats': '/chats',
      '/complaints/3': '/feedback',
      '/lessons/77': '/schedule',
      '/portal/homework/9': '/homework/9',
      '/portal/payments/': '/payments',
      '/portal/rules': '/rules',
      'https://app.oneenglish.kz/portal/notifications': '/notifications',
      '/something/else': '/home',
    };
    cases.forEach((link, route) => expect(mapServerLink(link), route, reason: '$link'));
  });
}
