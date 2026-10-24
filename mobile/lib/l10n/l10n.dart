import 'package:flutter/widgets.dart';

import 'gen/app_localizations.dart';

export 'gen/app_localizations.dart';

extension L10nX on BuildContext {
  AppLocalizations get t => AppLocalizations.of(this);
}

/// "Кабинет 12" for a bare number; the room's own name when the school already wrote one ("Каб. 2", "Зал").
String roomLabel(AppLocalizations t, String room) =>
    RegExp(r'^\d+[A-Za-zА-Яа-я]?$').hasMatch(room.trim()) ? t.room(room.trim()) : room;
