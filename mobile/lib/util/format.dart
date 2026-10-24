import 'package:intl/intl.dart';

import '../config.dart';

/// Wall-clock time in the school's time zone (Asia/Almaty, UTC+5), whatever the device zone is.
DateTime school(DateTime d) => d.toUtc().add(AppConfig.schoolUtcOffset);

/// "Now" in school time.
DateTime schoolNow() => school(DateTime.now());

DateTime dateOnly(DateTime d) => DateTime.utc(d.year, d.month, d.day);

String _loc(String locale) => locale == 'kk' ? 'kk' : 'ru';

String hm(DateTime d) => DateFormat('HH:mm').format(school(d));

String dayMonth(DateTime d, String locale) => DateFormat('d MMMM', _loc(locale)).format(school(d));
String dayMonthShort(DateTime d, String locale) => DateFormat('d MMM', _loc(locale)).format(school(d));
String dmy(DateTime d) => DateFormat('dd.MM.yyyy').format(school(d));
String weekdayShort(DateTime d, String locale) => _cap(DateFormat('EE', _loc(locale)).format(school(d)));
String weekdayLong(DateTime d, String locale) => _cap(DateFormat('EEEE', _loc(locale)).format(school(d)));
String monthName(DateTime d, String locale) => DateFormat('LLLL', _loc(locale)).format(school(d));

/// "Суббота, 24 октября".
String todayLine(String locale) {
  final n = DateTime.now();
  return '${weekdayLong(n, locale)}, ${dayMonth(n, locale)}';
}

String _cap(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);

/// 33 500 ₸ (amounts are whole tenge).
String money(int v) => '${num(v)} ₸';

/// 1 240 — thin non-breaking groups.
String num(int v) => NumberFormat.decimalPattern('ru').format(v).replaceAll(' ', ' ').replaceAll(' ', ' ');

/// +7 701 234 56 78 from any stored form.
String formatPhone(String phone) {
  final d = phone.replaceAll(RegExp(r'\D'), '');
  if (d.length == 11 && (d.startsWith('7') || d.startsWith('8'))) {
    return '+7 ${d.substring(1, 4)} ${d.substring(4, 7)} ${d.substring(7, 9)} ${d.substring(9)}';
  }
  return phone;
}

/// "+7 701 234 •• 78" — the code screen shows the number without revealing all of it.
String maskPhone(String phone) {
  final d = phone.replaceAll(RegExp(r'\D'), '');
  if (d.length != 11) return phone;
  return '+7 ${d.substring(1, 4)} ${d.substring(4, 7)} •• ${d.substring(9)}';
}

/// Digits after +7 typed by the user → "701 234 56 78".
String maskLocal(String digits) {
  final d = digits.replaceAll(RegExp(r'\D'), '');
  final b = StringBuffer();
  for (var i = 0; i < d.length && i < 10; i++) {
    if (i == 3 || i == 6 || i == 8) b.write(' ');
    b.write(d[i]);
  }
  return b.toString();
}

/// Phone-number-like sequences in a chat message (7+ digits with spaces, dashes or brackets).
final phonePattern = RegExp(r'(\+?\d[\d\s\-()]{8,}\d)');
