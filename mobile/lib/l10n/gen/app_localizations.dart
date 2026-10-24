import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_kk.dart';
import 'app_localizations_ru.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'gen/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('kk'),
    Locale('ru'),
  ];

  /// No description provided for @back.
  ///
  /// In ru, this message translates to:
  /// **'Назад'**
  String get back;

  /// No description provided for @navHome.
  ///
  /// In ru, this message translates to:
  /// **'Главная'**
  String get navHome;

  /// No description provided for @navSchedule.
  ///
  /// In ru, this message translates to:
  /// **'Расписание'**
  String get navSchedule;

  /// No description provided for @navHomework.
  ///
  /// In ru, this message translates to:
  /// **'Задания'**
  String get navHomework;

  /// No description provided for @navChats.
  ///
  /// In ru, this message translates to:
  /// **'Чаты'**
  String get navChats;

  /// No description provided for @navCoins.
  ///
  /// In ru, this message translates to:
  /// **'Коины'**
  String get navCoins;

  /// No description provided for @navPayments.
  ///
  /// In ru, this message translates to:
  /// **'Оплата'**
  String get navPayments;

  /// No description provided for @navNotifications.
  ///
  /// In ru, this message translates to:
  /// **'Уведомления'**
  String get navNotifications;

  /// No description provided for @navProfile.
  ///
  /// In ru, this message translates to:
  /// **'Профиль'**
  String get navProfile;

  /// No description provided for @retry.
  ///
  /// In ru, this message translates to:
  /// **'Повторить'**
  String get retry;

  /// No description provided for @cancel.
  ///
  /// In ru, this message translates to:
  /// **'Отмена'**
  String get cancel;

  /// No description provided for @loading.
  ///
  /// In ru, this message translates to:
  /// **'Загрузка…'**
  String get loading;

  /// No description provided for @send.
  ///
  /// In ru, this message translates to:
  /// **'Отправить'**
  String get send;

  /// No description provided for @search.
  ///
  /// In ru, this message translates to:
  /// **'Поиск'**
  String get search;

  /// No description provided for @call.
  ///
  /// In ru, this message translates to:
  /// **'Позвонить'**
  String get call;

  /// No description provided for @copy.
  ///
  /// In ru, this message translates to:
  /// **'Скопировать'**
  String get copy;

  /// No description provided for @copied.
  ///
  /// In ru, this message translates to:
  /// **'Скопировано'**
  String get copied;

  /// No description provided for @remove.
  ///
  /// In ru, this message translates to:
  /// **'Убрать'**
  String get remove;

  /// No description provided for @understood.
  ///
  /// In ru, this message translates to:
  /// **'Понятно'**
  String get understood;

  /// No description provided for @notNow.
  ///
  /// In ru, this message translates to:
  /// **'Не сейчас'**
  String get notNow;

  /// No description provided for @selected.
  ///
  /// In ru, this message translates to:
  /// **'Выбран'**
  String get selected;

  /// No description provided for @today.
  ///
  /// In ru, this message translates to:
  /// **'Сегодня'**
  String get today;

  /// No description provided for @yesterday.
  ///
  /// In ru, this message translates to:
  /// **'Вчера'**
  String get yesterday;

  /// No description provided for @you.
  ///
  /// In ru, this message translates to:
  /// **'Вы'**
  String get you;

  /// No description provided for @school.
  ///
  /// In ru, this message translates to:
  /// **'Школа'**
  String get school;

  /// No description provided for @branchName.
  ///
  /// In ru, this message translates to:
  /// **'Филиал {name}'**
  String branchName(String name);

  /// No description provided for @branchShort.
  ///
  /// In ru, this message translates to:
  /// **'Ваш филиал'**
  String get branchShort;

  /// No description provided for @errGeneric.
  ///
  /// In ru, this message translates to:
  /// **'Что-то пошло не так. Попробуйте ещё раз.'**
  String get errGeneric;

  /// No description provided for @errNetwork.
  ///
  /// In ru, this message translates to:
  /// **'Нет связи с сервером. Проверьте интернет.'**
  String get errNetwork;

  /// No description provided for @nothingFound.
  ///
  /// In ru, this message translates to:
  /// **'Ничего не найдено'**
  String get nothingFound;

  /// No description provided for @wdMon.
  ///
  /// In ru, this message translates to:
  /// **'Пн'**
  String get wdMon;

  /// No description provided for @wdTue.
  ///
  /// In ru, this message translates to:
  /// **'Вт'**
  String get wdTue;

  /// No description provided for @wdWed.
  ///
  /// In ru, this message translates to:
  /// **'Ср'**
  String get wdWed;

  /// No description provided for @wdThu.
  ///
  /// In ru, this message translates to:
  /// **'Чт'**
  String get wdThu;

  /// No description provided for @wdFri.
  ///
  /// In ru, this message translates to:
  /// **'Пт'**
  String get wdFri;

  /// No description provided for @wdSat.
  ///
  /// In ru, this message translates to:
  /// **'Сб'**
  String get wdSat;

  /// No description provided for @wdSun.
  ///
  /// In ru, this message translates to:
  /// **'Вс'**
  String get wdSun;

  /// No description provided for @roleParent.
  ///
  /// In ru, this message translates to:
  /// **'Родитель'**
  String get roleParent;

  /// No description provided for @roleTeacher.
  ///
  /// In ru, this message translates to:
  /// **'Преподаватель'**
  String get roleTeacher;

  /// No description provided for @roleManager.
  ///
  /// In ru, this message translates to:
  /// **'Менеджер'**
  String get roleManager;

  /// No description provided for @roleAdmin.
  ///
  /// In ru, this message translates to:
  /// **'Администратор'**
  String get roleAdmin;

  /// No description provided for @roleStaff.
  ///
  /// In ru, this message translates to:
  /// **'Школа'**
  String get roleStaff;

  /// No description provided for @splashFoot.
  ///
  /// In ru, this message translates to:
  /// **'Школа английского языка · Шымкент'**
  String get splashFoot;

  /// No description provided for @offlineTitle.
  ///
  /// In ru, this message translates to:
  /// **'Нет подключения'**
  String get offlineTitle;

  /// No description provided for @offlineText.
  ///
  /// In ru, this message translates to:
  /// **'Не удалось связаться с сервером. Проверьте интернет и попробуйте снова.'**
  String get offlineText;

  /// No description provided for @loginTitle.
  ///
  /// In ru, this message translates to:
  /// **'Вход'**
  String get loginTitle;

  /// No description provided for @loginText.
  ///
  /// In ru, this message translates to:
  /// **'Введите номер телефона, который вы оставили в школе.'**
  String get loginText;

  /// No description provided for @phoneLabel.
  ///
  /// In ru, this message translates to:
  /// **'Номер телефона'**
  String get phoneLabel;

  /// No description provided for @phoneInvalid.
  ///
  /// In ru, this message translates to:
  /// **'Введите номер полностью: +7 и 10 цифр'**
  String get phoneInvalid;

  /// No description provided for @codeChannel.
  ///
  /// In ru, this message translates to:
  /// **'Куда прислать код'**
  String get codeChannel;

  /// No description provided for @waFast.
  ///
  /// In ru, this message translates to:
  /// **'Быстрее всего'**
  String get waFast;

  /// No description provided for @smsSoon.
  ///
  /// In ru, this message translates to:
  /// **'Скоро'**
  String get smsSoon;

  /// No description provided for @getCode.
  ///
  /// In ru, this message translates to:
  /// **'Получить код'**
  String get getCode;

  /// No description provided for @noNumber.
  ///
  /// In ru, this message translates to:
  /// **'Номера нет в школе? Напишите нам в WhatsApp {phone}'**
  String noNumber(String phone);

  /// No description provided for @staffRejected.
  ///
  /// In ru, this message translates to:
  /// **'Это приложение для учеников и родителей. Сотрудники работают в веб-кабинете.'**
  String get staffRejected;

  /// No description provided for @codeTitle.
  ///
  /// In ru, this message translates to:
  /// **'Код из WhatsApp'**
  String get codeTitle;

  /// No description provided for @codeSent.
  ///
  /// In ru, this message translates to:
  /// **'Мы отправили 6-значный код на номер'**
  String get codeSent;

  /// No description provided for @codeWrong.
  ///
  /// In ru, this message translates to:
  /// **'Неверный код'**
  String get codeWrong;

  /// No description provided for @codeAgain.
  ///
  /// In ru, this message translates to:
  /// **'Отправить код ещё раз'**
  String get codeAgain;

  /// No description provided for @codeAgainIn.
  ///
  /// In ru, this message translates to:
  /// **'Отправить ещё раз через {time}'**
  String codeAgainIn(String time);

  /// No description provided for @codeResent.
  ///
  /// In ru, this message translates to:
  /// **'Код отправлен ещё раз'**
  String get codeResent;

  /// No description provided for @pinCreate.
  ///
  /// In ru, this message translates to:
  /// **'Придумайте PIN-код'**
  String get pinCreate;

  /// No description provided for @pinCreateText.
  ///
  /// In ru, this message translates to:
  /// **'4 цифры для быстрого входа. Без него вход — по коду из WhatsApp.'**
  String get pinCreateText;

  /// No description provided for @pinRepeat.
  ///
  /// In ru, this message translates to:
  /// **'Повторите PIN-код'**
  String get pinRepeat;

  /// No description provided for @pinMismatch.
  ///
  /// In ru, this message translates to:
  /// **'Коды не совпадают. Попробуйте ещё раз.'**
  String get pinMismatch;

  /// No description provided for @pinWeak.
  ///
  /// In ru, this message translates to:
  /// **'Слишком простой код. Не используйте 1111, 1234 или год рождения.'**
  String get pinWeak;

  /// No description provided for @pinHint.
  ///
  /// In ru, this message translates to:
  /// **'Код хранится только на этом телефоне'**
  String get pinHint;

  /// No description provided for @pinEnter.
  ///
  /// In ru, this message translates to:
  /// **'Здравствуйте, {name}'**
  String pinEnter(String name);

  /// No description provided for @pinWrong.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, one{Неверный код. Осталась {n} попытка} few{Неверный код. Осталось {n} попытки} many{Неверный код. Осталось {n} попыток} other{Неверный код. Осталось {n} попытки}}'**
  String pinWrong(int n);

  /// No description provided for @pinForgot.
  ///
  /// In ru, this message translates to:
  /// **'Забыли код? Войти по номеру'**
  String get pinForgot;

  /// No description provided for @pinTooMany.
  ///
  /// In ru, this message translates to:
  /// **'Слишком много попыток. Войдите заново по номеру телефона.'**
  String get pinTooMany;

  /// No description provided for @pinChange.
  ///
  /// In ru, this message translates to:
  /// **'Сменить PIN-код'**
  String get pinChange;

  /// No description provided for @pinSet.
  ///
  /// In ru, this message translates to:
  /// **'Установить PIN-код'**
  String get pinSet;

  /// No description provided for @pinChanged.
  ///
  /// In ru, this message translates to:
  /// **'PIN-код сохранён'**
  String get pinChanged;

  /// No description provided for @pinOff.
  ///
  /// In ru, this message translates to:
  /// **'Отключить PIN-код'**
  String get pinOff;

  /// No description provided for @pinOffTitle.
  ///
  /// In ru, this message translates to:
  /// **'Отключить PIN-код?'**
  String get pinOffTitle;

  /// No description provided for @pinOffText.
  ///
  /// In ru, this message translates to:
  /// **'Приложение будет открываться без кода. Вход по биометрии тоже отключится.'**
  String get pinOffText;

  /// No description provided for @erase.
  ///
  /// In ru, this message translates to:
  /// **'Стереть'**
  String get erase;

  /// No description provided for @bioTitleIos.
  ///
  /// In ru, this message translates to:
  /// **'Входить по Face ID?'**
  String get bioTitleIos;

  /// No description provided for @bioTitleAndroid.
  ///
  /// In ru, this message translates to:
  /// **'Входить по отпечатку?'**
  String get bioTitleAndroid;

  /// No description provided for @bioText.
  ///
  /// In ru, this message translates to:
  /// **'Это быстрее, чем PIN-код. Код остаётся запасным способом.'**
  String get bioText;

  /// No description provided for @bioEnableIos.
  ///
  /// In ru, this message translates to:
  /// **'Включить Face ID'**
  String get bioEnableIos;

  /// No description provided for @bioEnableAndroid.
  ///
  /// In ru, this message translates to:
  /// **'Включить отпечаток'**
  String get bioEnableAndroid;

  /// No description provided for @bioUse.
  ///
  /// In ru, this message translates to:
  /// **'Войти по биометрии'**
  String get bioUse;

  /// No description provided for @bioReason.
  ///
  /// In ru, this message translates to:
  /// **'Подтвердите вход в One English'**
  String get bioReason;

  /// No description provided for @bioToggleIos.
  ///
  /// In ru, this message translates to:
  /// **'Вход по Face ID'**
  String get bioToggleIos;

  /// No description provided for @bioToggleAndroid.
  ///
  /// In ru, this message translates to:
  /// **'Вход по отпечатку'**
  String get bioToggleAndroid;

  /// No description provided for @autolock.
  ///
  /// In ru, this message translates to:
  /// **'Автоблокировка'**
  String get autolock;

  /// No description provided for @autolockText.
  ///
  /// In ru, this message translates to:
  /// **'Спрашивать PIN-код после выхода из приложения'**
  String get autolockText;

  /// No description provided for @autolockNow.
  ///
  /// In ru, this message translates to:
  /// **'Сразу'**
  String get autolockNow;

  /// No description provided for @minutesN.
  ///
  /// In ru, this message translates to:
  /// **'{n} мин'**
  String minutesN(int n);

  /// No description provided for @blockedTitle.
  ///
  /// In ru, this message translates to:
  /// **'Доступ приостановлен'**
  String get blockedTitle;

  /// No description provided for @blockedText.
  ///
  /// In ru, this message translates to:
  /// **'Занятия закончились, а оплата не поступила. После оплаты всё откроется автоматически.'**
  String get blockedText;

  /// No description provided for @blockedShort.
  ///
  /// In ru, this message translates to:
  /// **'Доступ приостановлен'**
  String get blockedShort;

  /// No description provided for @toPayments.
  ///
  /// In ru, this message translates to:
  /// **'К оплате'**
  String get toPayments;

  /// No description provided for @noChildren.
  ///
  /// In ru, this message translates to:
  /// **'Детей пока нет'**
  String get noChildren;

  /// No description provided for @noChildrenText.
  ///
  /// In ru, this message translates to:
  /// **'Школа ещё не привязала ребёнка к вашему номеру. Напишите менеджеру.'**
  String get noChildrenText;

  /// No description provided for @helloStudent.
  ///
  /// In ru, this message translates to:
  /// **'Привет, {name}!'**
  String helloStudent(String name);

  /// No description provided for @helloParent.
  ///
  /// In ru, this message translates to:
  /// **'Здравствуйте, {name}'**
  String helloParent(String name);

  /// No description provided for @nextLesson.
  ///
  /// In ru, this message translates to:
  /// **'Следующий урок'**
  String get nextLesson;

  /// No description provided for @lessonNow.
  ///
  /// In ru, this message translates to:
  /// **'Идёт сейчас'**
  String get lessonNow;

  /// No description provided for @inDays.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, one{через {n} день} few{через {n} дня} many{через {n} дней} other{через {n} дня}}'**
  String inDays(int n);

  /// No description provided for @inHoursMinutes.
  ///
  /// In ru, this message translates to:
  /// **'через {h} ч {m} мин'**
  String inHoursMinutes(int h, int m);

  /// No description provided for @inMinutes.
  ///
  /// In ru, this message translates to:
  /// **'через {m} мин'**
  String inMinutes(int m);

  /// No description provided for @room.
  ///
  /// In ru, this message translates to:
  /// **'Кабинет {room}'**
  String room(String room);

  /// No description provided for @individualLesson.
  ///
  /// In ru, this message translates to:
  /// **'Индивидуальное занятие'**
  String get individualLesson;

  /// No description provided for @lessonsLeft.
  ///
  /// In ru, this message translates to:
  /// **'Осталось уроков'**
  String get lessonsLeft;

  /// No description provided for @ofN.
  ///
  /// In ru, this message translates to:
  /// **'из {n}'**
  String ofN(int n);

  /// No description provided for @heldN.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, one{Проведён {n} урок} few{Проведено {n} урока} many{Проведено {n} уроков} other{Проведено {n} урока}}'**
  String heldN(int n);

  /// No description provided for @perWeek.
  ///
  /// In ru, this message translates to:
  /// **'+{n} за неделю'**
  String perWeek(int n);

  /// No description provided for @myBalance.
  ///
  /// In ru, this message translates to:
  /// **'Мои коины'**
  String get myBalance;

  /// No description provided for @hwToday.
  ///
  /// In ru, this message translates to:
  /// **'Задания на сегодня'**
  String get hwToday;

  /// No description provided for @dueAt.
  ///
  /// In ru, this message translates to:
  /// **'до {time}'**
  String dueAt(String time);

  /// No description provided for @hwCheckedGrade.
  ///
  /// In ru, this message translates to:
  /// **'Проверено · {grade}'**
  String hwCheckedGrade(int grade);

  /// No description provided for @hwTodayAt.
  ///
  /// In ru, this message translates to:
  /// **'Сегодня до {time}'**
  String hwTodayAt(String time);

  /// No description provided for @allTasks.
  ///
  /// In ru, this message translates to:
  /// **'Все задания'**
  String get allTasks;

  /// No description provided for @attendanceMonth.
  ///
  /// In ru, this message translates to:
  /// **'Посещаемость за месяц'**
  String get attendanceMonth;

  /// No description provided for @presentOf.
  ///
  /// In ru, this message translates to:
  /// **'Был на {a} из {b}'**
  String presentOf(int a, int b);

  /// No description provided for @debtTitle.
  ///
  /// In ru, this message translates to:
  /// **'Есть долг'**
  String get debtTitle;

  /// No description provided for @debtText.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, one{Долг {n} урок — пополните баланс} few{Долг {n} урока — пополните баланс} many{Долг {n} уроков — пополните баланс} other{Долг {n} урока — пополните баланс}}'**
  String debtText(int n);

  /// No description provided for @lowTitle.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, =0{Уроки закончились} one{Остался {n} урок} few{Осталось {n} урока} many{Осталось {n} уроков} other{Осталось {n} урока}}'**
  String lowTitle(int n);

  /// No description provided for @lowText.
  ///
  /// In ru, this message translates to:
  /// **'Пополните баланс, чтобы не прерывать занятия'**
  String get lowText;

  /// No description provided for @consentTitle.
  ///
  /// In ru, this message translates to:
  /// **'Согласие на запись уроков'**
  String get consentTitle;

  /// No description provided for @consentText.
  ///
  /// In ru, this message translates to:
  /// **'Подпишите согласие в разделе «Правила»'**
  String get consentText;

  /// No description provided for @avgGrade.
  ///
  /// In ru, this message translates to:
  /// **'Средняя оценка'**
  String get avgGrade;

  /// No description provided for @avgFor.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, one{{month} · {n} оценка} few{{month} · {n} оценки} many{{month} · {n} оценок} other{{month} · {n} оценки}}'**
  String avgFor(String month, int n);

  /// No description provided for @attendanceOf.
  ///
  /// In ru, this message translates to:
  /// **'Посещаемость · {month}'**
  String attendanceOf(String month);

  /// No description provided for @nOfM.
  ///
  /// In ru, this message translates to:
  /// **'{a} из {b}'**
  String nOfM(int a, int b);

  /// No description provided for @stPresent.
  ///
  /// In ru, this message translates to:
  /// **'Был'**
  String get stPresent;

  /// No description provided for @stLate.
  ///
  /// In ru, this message translates to:
  /// **'Опоздал'**
  String get stLate;

  /// No description provided for @stAbsent.
  ///
  /// In ru, this message translates to:
  /// **'Не был'**
  String get stAbsent;

  /// No description provided for @stExcused.
  ///
  /// In ru, this message translates to:
  /// **'Уважительная'**
  String get stExcused;

  /// No description provided for @stAhead.
  ///
  /// In ru, this message translates to:
  /// **'Впереди'**
  String get stAhead;

  /// No description provided for @progress.
  ///
  /// In ru, this message translates to:
  /// **'Успеваемость'**
  String get progress;

  /// No description provided for @myProgress.
  ///
  /// In ru, this message translates to:
  /// **'Мои успехи'**
  String get myProgress;

  /// No description provided for @monthLessons.
  ///
  /// In ru, this message translates to:
  /// **'Уроков'**
  String get monthLessons;

  /// No description provided for @monthPresent.
  ///
  /// In ru, this message translates to:
  /// **'Посетил'**
  String get monthPresent;

  /// No description provided for @monthRate.
  ///
  /// In ru, this message translates to:
  /// **'Посещаемость'**
  String get monthRate;

  /// No description provided for @thisWeek.
  ///
  /// In ru, this message translates to:
  /// **'Эта неделя'**
  String get thisWeek;

  /// No description provided for @prevWeek.
  ///
  /// In ru, this message translates to:
  /// **'Прошлая неделя'**
  String get prevWeek;

  /// No description provided for @nextWeek.
  ///
  /// In ru, this message translates to:
  /// **'Следующая неделя'**
  String get nextWeek;

  /// No description provided for @noLessons.
  ///
  /// In ru, this message translates to:
  /// **'Уроков нет'**
  String get noLessons;

  /// No description provided for @noLessonsWeek.
  ///
  /// In ru, this message translates to:
  /// **'На этой неделе уроков нет'**
  String get noLessonsWeek;

  /// No description provided for @cancelled.
  ///
  /// In ru, this message translates to:
  /// **'Отменён'**
  String get cancelled;

  /// No description provided for @cancelledOn.
  ///
  /// In ru, this message translates to:
  /// **'Урок {day} в {time} отменён'**
  String cancelledOn(String day, String time);

  /// No description provided for @held.
  ///
  /// In ru, this message translates to:
  /// **'Проведён'**
  String get held;

  /// No description provided for @teacherComment.
  ///
  /// In ru, this message translates to:
  /// **'Комментарий преподавателя'**
  String get teacherComment;

  /// No description provided for @rateLesson.
  ///
  /// In ru, this message translates to:
  /// **'Оцените урок'**
  String get rateLesson;

  /// No description provided for @yourRating.
  ///
  /// In ru, this message translates to:
  /// **'Ваша оценка'**
  String get yourRating;

  /// No description provided for @rated.
  ///
  /// In ru, this message translates to:
  /// **'Спасибо за оценку!'**
  String get rated;

  /// No description provided for @starsN.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, one{{n} звезда} few{{n} звезды} many{{n} звёзд} other{{n} звезды}}'**
  String starsN(int n);

  /// No description provided for @lessonGrades.
  ///
  /// In ru, this message translates to:
  /// **'Оценки за урок'**
  String get lessonGrades;

  /// No description provided for @hwActive.
  ///
  /// In ru, this message translates to:
  /// **'Активные'**
  String get hwActive;

  /// No description provided for @hwActiveN.
  ///
  /// In ru, this message translates to:
  /// **'Активные · {n}'**
  String hwActiveN(int n);

  /// No description provided for @hwReview.
  ///
  /// In ru, this message translates to:
  /// **'На проверке'**
  String get hwReview;

  /// No description provided for @hwChecked.
  ///
  /// In ru, this message translates to:
  /// **'Проверено'**
  String get hwChecked;

  /// No description provided for @hwAssigned.
  ///
  /// In ru, this message translates to:
  /// **'Задано'**
  String get hwAssigned;

  /// No description provided for @hwOverdue.
  ///
  /// In ru, this message translates to:
  /// **'Просрочено'**
  String get hwOverdue;

  /// No description provided for @hwSubmitted.
  ///
  /// In ru, this message translates to:
  /// **'Сдано'**
  String get hwSubmitted;

  /// No description provided for @hwEmpty.
  ///
  /// In ru, this message translates to:
  /// **'Заданий нет'**
  String get hwEmpty;

  /// No description provided for @hwNone.
  ///
  /// In ru, this message translates to:
  /// **'Здесь пока пусто'**
  String get hwNone;

  /// No description provided for @hwNoneActive.
  ///
  /// In ru, this message translates to:
  /// **'Все задания сделаны'**
  String get hwNoneActive;

  /// No description provided for @hwNotFound.
  ///
  /// In ru, this message translates to:
  /// **'Задание не найдено'**
  String get hwNotFound;

  /// No description provided for @hwTask.
  ///
  /// In ru, this message translates to:
  /// **'Задание'**
  String get hwTask;

  /// No description provided for @dueFull.
  ///
  /// In ru, this message translates to:
  /// **'Сдать до {date}'**
  String dueFull(String date);

  /// No description provided for @myAnswer.
  ///
  /// In ru, this message translates to:
  /// **'Мой ответ'**
  String get myAnswer;

  /// No description provided for @hwAnswerHint.
  ///
  /// In ru, this message translates to:
  /// **'Напишите ответ…'**
  String get hwAnswerHint;

  /// No description provided for @hwOneFile.
  ///
  /// In ru, this message translates to:
  /// **'Можно приложить один файл: фото, голос или документ'**
  String get hwOneFile;

  /// No description provided for @hwFile.
  ///
  /// In ru, this message translates to:
  /// **'Файл'**
  String get hwFile;

  /// No description provided for @hwSubmit.
  ///
  /// In ru, this message translates to:
  /// **'Сдать задание'**
  String get hwSubmit;

  /// No description provided for @hwSent.
  ///
  /// In ru, this message translates to:
  /// **'Задание отправлено на проверку'**
  String get hwSent;

  /// No description provided for @hwRedo.
  ///
  /// In ru, this message translates to:
  /// **'Переделать'**
  String get hwRedo;

  /// No description provided for @hwNoAnswer.
  ///
  /// In ru, this message translates to:
  /// **'Напишите ответ или приложите файл'**
  String get hwNoAnswer;

  /// No description provided for @hwNoAnswerParent.
  ///
  /// In ru, this message translates to:
  /// **'Ученик ещё не сдал это задание'**
  String get hwNoAnswerParent;

  /// No description provided for @photo.
  ///
  /// In ru, this message translates to:
  /// **'Фото'**
  String get photo;

  /// No description provided for @camera.
  ///
  /// In ru, this message translates to:
  /// **'Камера'**
  String get camera;

  /// No description provided for @gallery.
  ///
  /// In ru, this message translates to:
  /// **'Галерея'**
  String get gallery;

  /// No description provided for @voice.
  ///
  /// In ru, this message translates to:
  /// **'Голос'**
  String get voice;

  /// No description provided for @file.
  ///
  /// In ru, this message translates to:
  /// **'Файл'**
  String get file;

  /// No description provided for @stop.
  ///
  /// In ru, this message translates to:
  /// **'Стоп'**
  String get stop;

  /// No description provided for @play.
  ///
  /// In ru, this message translates to:
  /// **'Слушать'**
  String get play;

  /// No description provided for @pause.
  ///
  /// In ru, this message translates to:
  /// **'Пауза'**
  String get pause;

  /// No description provided for @uploading.
  ///
  /// In ru, this message translates to:
  /// **'Загружаем файл…'**
  String get uploading;

  /// No description provided for @micDenied.
  ///
  /// In ru, this message translates to:
  /// **'Нет доступа к микрофону. Разрешите его в настройках телефона.'**
  String get micDenied;

  /// No description provided for @recording.
  ///
  /// In ru, this message translates to:
  /// **'Запись {time}'**
  String recording(String time);

  /// No description provided for @recordVoice.
  ///
  /// In ru, this message translates to:
  /// **'Записать голосовое'**
  String get recordVoice;

  /// No description provided for @progressAndGrades.
  ///
  /// In ru, this message translates to:
  /// **'Успеваемость и оценки'**
  String get progressAndGrades;

  /// No description provided for @level.
  ///
  /// In ru, this message translates to:
  /// **'Уровень'**
  String get level;

  /// No description provided for @average.
  ///
  /// In ru, this message translates to:
  /// **'Средняя'**
  String get average;

  /// No description provided for @noMarks.
  ///
  /// In ru, this message translates to:
  /// **'Оценок пока нет'**
  String get noMarks;

  /// No description provided for @noTests.
  ///
  /// In ru, this message translates to:
  /// **'Тестов пока не было'**
  String get noTests;

  /// No description provided for @attendanceHistory.
  ///
  /// In ru, this message translates to:
  /// **'История посещений'**
  String get attendanceHistory;

  /// No description provided for @debt.
  ///
  /// In ru, this message translates to:
  /// **'Долг'**
  String get debt;

  /// No description provided for @notCharged.
  ///
  /// In ru, this message translates to:
  /// **'Не списан'**
  String get notCharged;

  /// No description provided for @debtLessonsN.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, one{{n} урок в долг} few{{n} урока в долг} many{{n} уроков в долг} other{{n} урока в долг}}'**
  String debtLessonsN(int n);

  /// No description provided for @pricePer.
  ///
  /// In ru, this message translates to:
  /// **'{price} за урок'**
  String pricePer(String price);

  /// No description provided for @needPayment.
  ///
  /// In ru, this message translates to:
  /// **'Нужна оплата'**
  String get needPayment;

  /// No description provided for @howToPay.
  ///
  /// In ru, this message translates to:
  /// **'Как оплатить'**
  String get howToPay;

  /// No description provided for @payHowText.
  ///
  /// In ru, this message translates to:
  /// **'Оплатить можно в филиале наличными, картой или переводом. Онлайн-оплата в приложении появится позже.'**
  String get payHowText;

  /// No description provided for @onlineSoon.
  ///
  /// In ru, this message translates to:
  /// **'Онлайн-оплата скоро появится'**
  String get onlineSoon;

  /// No description provided for @payFor.
  ///
  /// In ru, this message translates to:
  /// **'Оплата за {name}'**
  String payFor(String name);

  /// No description provided for @callBranch.
  ///
  /// In ru, this message translates to:
  /// **'Позвонить в филиал {name}'**
  String callBranch(String name);

  /// No description provided for @writeManager.
  ///
  /// In ru, this message translates to:
  /// **'Написать менеджеру'**
  String get writeManager;

  /// No description provided for @lessonsN.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, one{{n} урок} few{{n} урока} many{{n} уроков} other{{n} урока}}'**
  String lessonsN(int n);

  /// No description provided for @onBalance.
  ///
  /// In ru, this message translates to:
  /// **'На балансе {sum}'**
  String onBalance(String sum);

  /// No description provided for @history.
  ///
  /// In ru, this message translates to:
  /// **'История'**
  String get history;

  /// No description provided for @noPayments.
  ///
  /// In ru, this message translates to:
  /// **'Оплат пока нет'**
  String get noPayments;

  /// No description provided for @refunded.
  ///
  /// In ru, this message translates to:
  /// **'Возврат {sum}'**
  String refunded(String sum);

  /// No description provided for @payCategory.
  ///
  /// In ru, this message translates to:
  /// **'{c, select, course{Курс} book{Учебник} other{Оплата}}'**
  String payCategory(String c);

  /// No description provided for @payCash.
  ///
  /// In ru, this message translates to:
  /// **'Наличные'**
  String get payCash;

  /// No description provided for @payCard.
  ///
  /// In ru, this message translates to:
  /// **'Карта'**
  String get payCard;

  /// No description provided for @payTransfer.
  ///
  /// In ru, this message translates to:
  /// **'Перевод'**
  String get payTransfer;

  /// No description provided for @bookPurchase.
  ///
  /// In ru, this message translates to:
  /// **'Покупка учебника'**
  String get bookPurchase;

  /// No description provided for @myBooks.
  ///
  /// In ru, this message translates to:
  /// **'Учебники'**
  String get myBooks;

  /// No description provided for @noBooks.
  ///
  /// In ru, this message translates to:
  /// **'Учебников пока нет'**
  String get noBooks;

  /// No description provided for @noBooksText.
  ///
  /// In ru, this message translates to:
  /// **'Здесь появятся учебники, купленные в школе'**
  String get noBooksText;

  /// No description provided for @booksLevel.
  ///
  /// In ru, this message translates to:
  /// **'Уровень {level}'**
  String booksLevel(String level);

  /// No description provided for @chat.
  ///
  /// In ru, this message translates to:
  /// **'Чат'**
  String get chat;

  /// No description provided for @noChats.
  ///
  /// In ru, this message translates to:
  /// **'Чатов пока нет'**
  String get noChats;

  /// No description provided for @noChatsText.
  ///
  /// In ru, this message translates to:
  /// **'Напишите преподавателю или менеджеру — кнопка справа вверху'**
  String get noChatsText;

  /// No description provided for @newChat.
  ///
  /// In ru, this message translates to:
  /// **'Новый чат'**
  String get newChat;

  /// No description provided for @searchPeople.
  ///
  /// In ru, this message translates to:
  /// **'Поиск по имени'**
  String get searchPeople;

  /// No description provided for @contactsHint.
  ///
  /// In ru, this message translates to:
  /// **'Можно написать преподавателям своих групп и менеджерам филиала'**
  String get contactsHint;

  /// No description provided for @noContacts.
  ///
  /// In ru, this message translates to:
  /// **'Некому написать'**
  String get noContacts;

  /// No description provided for @membersN.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, one{{n} участник} few{{n} участника} many{{n} участников} other{{n} участника}}'**
  String membersN(int n);

  /// No description provided for @chatNotice.
  ///
  /// In ru, this message translates to:
  /// **'Переписка сохраняется в школе. Не отправляйте пароли и номера карт.'**
  String get chatNotice;

  /// No description provided for @chatRulesTitle.
  ///
  /// In ru, this message translates to:
  /// **'Правила чата'**
  String get chatRulesTitle;

  /// No description provided for @chatRule1.
  ///
  /// In ru, this message translates to:
  /// **'Общайтесь вежливо — переписку видит администрация школы.'**
  String get chatRule1;

  /// No description provided for @chatRule2.
  ///
  /// In ru, this message translates to:
  /// **'Ученикам нельзя обмениваться номерами телефонов с преподавателями.'**
  String get chatRule2;

  /// No description provided for @chatRule3.
  ///
  /// In ru, this message translates to:
  /// **'Если что-то не так — нажмите на сообщение и выберите «Пожаловаться».'**
  String get chatRule3;

  /// No description provided for @noMessages.
  ///
  /// In ru, this message translates to:
  /// **'Сообщений пока нет'**
  String get noMessages;

  /// No description provided for @firstMessage.
  ///
  /// In ru, this message translates to:
  /// **'Напишите первое сообщение'**
  String get firstMessage;

  /// No description provided for @message.
  ///
  /// In ru, this message translates to:
  /// **'Сообщение'**
  String get message;

  /// No description provided for @attach.
  ///
  /// In ru, this message translates to:
  /// **'Прикрепить'**
  String get attach;

  /// No description provided for @pinned.
  ///
  /// In ru, this message translates to:
  /// **'Закреплённое'**
  String get pinned;

  /// No description provided for @pinnedN.
  ///
  /// In ru, this message translates to:
  /// **'Закреплённые · {n}'**
  String pinnedN(int n);

  /// No description provided for @messageHidden.
  ///
  /// In ru, this message translates to:
  /// **'Сообщение скрыто'**
  String get messageHidden;

  /// No description provided for @hideMessage.
  ///
  /// In ru, this message translates to:
  /// **'Скрыть'**
  String get hideMessage;

  /// No description provided for @hideTitle.
  ///
  /// In ru, this message translates to:
  /// **'Скрыть сообщение?'**
  String get hideTitle;

  /// No description provided for @hideText.
  ///
  /// In ru, this message translates to:
  /// **'Сообщение исчезнет у всех участников чата.'**
  String get hideText;

  /// No description provided for @report.
  ///
  /// In ru, this message translates to:
  /// **'Пожаловаться'**
  String get report;

  /// No description provided for @reportWhy.
  ///
  /// In ru, this message translates to:
  /// **'Что не так с сообщением?'**
  String get reportWhy;

  /// No description provided for @reportHint.
  ///
  /// In ru, this message translates to:
  /// **'Жалобу рассмотрит администрация школы'**
  String get reportHint;

  /// No description provided for @reasonInsult.
  ///
  /// In ru, this message translates to:
  /// **'Грубость или оскорбление'**
  String get reasonInsult;

  /// No description provided for @reasonSpam.
  ///
  /// In ru, this message translates to:
  /// **'Спам или реклама'**
  String get reasonSpam;

  /// No description provided for @reasonPersonal.
  ///
  /// In ru, this message translates to:
  /// **'Просят личные контакты'**
  String get reasonPersonal;

  /// No description provided for @reasonOther.
  ///
  /// In ru, this message translates to:
  /// **'Другое'**
  String get reasonOther;

  /// No description provided for @reportSubject.
  ///
  /// In ru, this message translates to:
  /// **'Жалоба на сообщение в чате «{chat}»'**
  String reportSubject(String chat);

  /// No description provided for @reportBody.
  ///
  /// In ru, this message translates to:
  /// **'Причина: {reason}\nАвтор: {author}\nВремя: {at}\nСообщение: {text}\nID сообщения: {id}'**
  String reportBody(
    String reason,
    String author,
    String at,
    String text,
    int id,
  );

  /// No description provided for @reportSent.
  ///
  /// In ru, this message translates to:
  /// **'Жалоба отправлена. Ответ до {date}'**
  String reportSent(String date);

  /// No description provided for @phoneBlockedTitle.
  ///
  /// In ru, this message translates to:
  /// **'Номер телефона в сообщении'**
  String get phoneBlockedTitle;

  /// No description provided for @phoneBlockedText.
  ///
  /// In ru, this message translates to:
  /// **'Ученикам нельзя отправлять номера телефонов в чатах школы. Уберите номер, чтобы отправить.'**
  String get phoneBlockedText;

  /// No description provided for @phoneShort.
  ///
  /// In ru, this message translates to:
  /// **'Уберите номер телефона'**
  String get phoneShort;

  /// No description provided for @removeNumber.
  ///
  /// In ru, this message translates to:
  /// **'Убрать номер'**
  String get removeNumber;

  /// No description provided for @shop.
  ///
  /// In ru, this message translates to:
  /// **'Магазин'**
  String get shop;

  /// No description provided for @rating.
  ///
  /// In ru, this message translates to:
  /// **'Рейтинг'**
  String get rating;

  /// No description provided for @orders.
  ///
  /// In ru, this message translates to:
  /// **'Мои заказы'**
  String get orders;

  /// No description provided for @exchange.
  ///
  /// In ru, this message translates to:
  /// **'Обменять'**
  String get exchange;

  /// No description provided for @buyTitle.
  ///
  /// In ru, this message translates to:
  /// **'Обменять коины?'**
  String get buyTitle;

  /// No description provided for @buyText.
  ///
  /// In ru, this message translates to:
  /// **'«{item}» за {price} коинов. Забрать можно у администратора филиала.'**
  String buyText(String item, String price);

  /// No description provided for @ordered.
  ///
  /// In ru, this message translates to:
  /// **'Заказ «{item}» оформлен'**
  String ordered(String item);

  /// No description provided for @needMore.
  ///
  /// In ru, this message translates to:
  /// **'Не хватает {n}'**
  String needMore(String n);

  /// No description provided for @outOfStock.
  ///
  /// In ru, this message translates to:
  /// **'Нет в наличии'**
  String get outOfStock;

  /// No description provided for @shopEmpty.
  ///
  /// In ru, this message translates to:
  /// **'Магазин пока пуст'**
  String get shopEmpty;

  /// No description provided for @openOrders.
  ///
  /// In ru, this message translates to:
  /// **'{n, plural, one{{n} заказ ждёт выдачи} few{{n} заказа ждут выдачи} many{{n} заказов ждут выдачи} other{{n} заказа ждут выдачи}}'**
  String openOrders(int n);

  /// No description provided for @groupN.
  ///
  /// In ru, this message translates to:
  /// **'Группа {name}'**
  String groupN(String name);

  /// No description provided for @noRating.
  ///
  /// In ru, this message translates to:
  /// **'Рейтинг пока пуст'**
  String get noRating;

  /// No description provided for @noCoinHistory.
  ///
  /// In ru, this message translates to:
  /// **'Начислений пока нет'**
  String get noCoinHistory;

  /// No description provided for @coinAward.
  ///
  /// In ru, this message translates to:
  /// **'Начисление'**
  String get coinAward;

  /// No description provided for @coinOrder.
  ///
  /// In ru, this message translates to:
  /// **'Обмен: {item}'**
  String coinOrder(String item);

  /// No description provided for @coinOrderCancelled.
  ///
  /// In ru, this message translates to:
  /// **'Возврат за отменённый заказ'**
  String get coinOrderCancelled;

  /// No description provided for @coinsN.
  ///
  /// In ru, this message translates to:
  /// **'{n} коинов'**
  String coinsN(int n);

  /// No description provided for @noOrders.
  ///
  /// In ru, this message translates to:
  /// **'Заказов пока нет'**
  String get noOrders;

  /// No description provided for @orderPlaced.
  ///
  /// In ru, this message translates to:
  /// **'Оформлен'**
  String get orderPlaced;

  /// No description provided for @orderPlacedHint.
  ///
  /// In ru, this message translates to:
  /// **'Администратор подготовит подарок'**
  String get orderPlacedHint;

  /// No description provided for @orderReady.
  ///
  /// In ru, this message translates to:
  /// **'Готов к выдаче'**
  String get orderReady;

  /// No description provided for @orderReadyHint.
  ///
  /// In ru, this message translates to:
  /// **'Заберите у администратора филиала'**
  String get orderReadyHint;

  /// No description provided for @orderIssued.
  ///
  /// In ru, this message translates to:
  /// **'Выдан'**
  String get orderIssued;

  /// No description provided for @orderCancelled.
  ///
  /// In ru, this message translates to:
  /// **'Заказ отменён, коины вернулись'**
  String get orderCancelled;

  /// No description provided for @orderCancelledShort.
  ///
  /// In ru, this message translates to:
  /// **'Отменён'**
  String get orderCancelledShort;

  /// No description provided for @pickUp.
  ///
  /// In ru, this message translates to:
  /// **'Забрать'**
  String get pickUp;

  /// No description provided for @cancelOrder.
  ///
  /// In ru, this message translates to:
  /// **'Отменить заказ'**
  String get cancelOrder;

  /// No description provided for @cancelOrderTitle.
  ///
  /// In ru, this message translates to:
  /// **'Отменить заказ?'**
  String get cancelOrderTitle;

  /// No description provided for @cancelOrderText.
  ///
  /// In ru, this message translates to:
  /// **'«{item}» — {coins} коинов вернутся на баланс.'**
  String cancelOrderText(String item, int coins);

  /// No description provided for @trioLeft.
  ///
  /// In ru, this message translates to:
  /// **'уроков'**
  String get trioLeft;

  /// No description provided for @trioCoins.
  ///
  /// In ru, this message translates to:
  /// **'коинов'**
  String get trioCoins;

  /// No description provided for @trioStars.
  ///
  /// In ru, this message translates to:
  /// **'звёзд'**
  String get trioStars;

  /// No description provided for @feedback.
  ///
  /// In ru, this message translates to:
  /// **'Жалобы и предложения'**
  String get feedback;

  /// No description provided for @feedbackSubtitle.
  ///
  /// In ru, this message translates to:
  /// **'Напишите, что можно улучшить. Ответим в течение 3 рабочих дней.'**
  String get feedbackSubtitle;

  /// No description provided for @feedbackNew.
  ///
  /// In ru, this message translates to:
  /// **'Новое обращение'**
  String get feedbackNew;

  /// No description provided for @subject.
  ///
  /// In ru, this message translates to:
  /// **'Тема'**
  String get subject;

  /// No description provided for @subjectHint.
  ///
  /// In ru, this message translates to:
  /// **'Коротко о сути'**
  String get subjectHint;

  /// No description provided for @subjectRequired.
  ///
  /// In ru, this message translates to:
  /// **'Укажите тему (от 3 символов)'**
  String get subjectRequired;

  /// No description provided for @complaintBody.
  ///
  /// In ru, this message translates to:
  /// **'Подробности'**
  String get complaintBody;

  /// No description provided for @complaintBodyHint.
  ///
  /// In ru, this message translates to:
  /// **'Что произошло, когда и с кем'**
  String get complaintBodyHint;

  /// No description provided for @bodyRequired.
  ///
  /// In ru, this message translates to:
  /// **'Опишите подробнее (от 10 символов)'**
  String get bodyRequired;

  /// No description provided for @against.
  ///
  /// In ru, this message translates to:
  /// **'О преподавателе'**
  String get against;

  /// No description provided for @againstHint.
  ///
  /// In ru, this message translates to:
  /// **'Если обращение о преподавателе — выберите его, оно уйдёт руководству, а не ему'**
  String get againstHint;

  /// No description provided for @nobody.
  ///
  /// In ru, this message translates to:
  /// **'Не о конкретном человеке'**
  String get nobody;

  /// No description provided for @teacherOf.
  ///
  /// In ru, this message translates to:
  /// **'Преподаватель {name}'**
  String teacherOf(String name);

  /// No description provided for @feedbackNote.
  ///
  /// In ru, this message translates to:
  /// **'Обращение увидят только руководители школы.'**
  String get feedbackNote;

  /// No description provided for @complaintSent.
  ///
  /// In ru, this message translates to:
  /// **'Обращение отправлено. Ответ до {date}'**
  String complaintSent(String date);

  /// No description provided for @feedbackHistory.
  ///
  /// In ru, this message translates to:
  /// **'Мои обращения'**
  String get feedbackHistory;

  /// No description provided for @feedbackEmpty.
  ///
  /// In ru, this message translates to:
  /// **'Обращений пока нет'**
  String get feedbackEmpty;

  /// No description provided for @feedbackEmptyText.
  ///
  /// In ru, this message translates to:
  /// **'Здесь появятся ваши жалобы и предложения с ответами'**
  String get feedbackEmptyText;

  /// No description provided for @sentAt.
  ///
  /// In ru, this message translates to:
  /// **'Отправлено {date}'**
  String sentAt(String date);

  /// No description provided for @dueAnswer.
  ///
  /// In ru, this message translates to:
  /// **'ответ до {date}'**
  String dueAnswer(String date);

  /// No description provided for @answer.
  ///
  /// In ru, this message translates to:
  /// **'Ответ школы'**
  String get answer;

  /// No description provided for @appeal.
  ///
  /// In ru, this message translates to:
  /// **'Не согласен с ответом'**
  String get appeal;

  /// No description provided for @appealTitle.
  ///
  /// In ru, this message translates to:
  /// **'Обжаловать ответ?'**
  String get appealTitle;

  /// No description provided for @appealText.
  ///
  /// In ru, this message translates to:
  /// **'Обращение передадут операционному директору.'**
  String get appealText;

  /// No description provided for @appealed.
  ///
  /// In ru, this message translates to:
  /// **'Передано операционному директору'**
  String get appealed;

  /// No description provided for @cNew.
  ///
  /// In ru, this message translates to:
  /// **'Новое'**
  String get cNew;

  /// No description provided for @cAcknowledged.
  ///
  /// In ru, this message translates to:
  /// **'Принято'**
  String get cAcknowledged;

  /// No description provided for @cInvestigating.
  ///
  /// In ru, this message translates to:
  /// **'Разбираемся'**
  String get cInvestigating;

  /// No description provided for @cAnswered.
  ///
  /// In ru, this message translates to:
  /// **'Есть ответ'**
  String get cAnswered;

  /// No description provided for @cAppealed.
  ///
  /// In ru, this message translates to:
  /// **'Обжаловано'**
  String get cAppealed;

  /// No description provided for @cClosed.
  ///
  /// In ru, this message translates to:
  /// **'Закрыто'**
  String get cClosed;

  /// No description provided for @rulesTitle.
  ///
  /// In ru, this message translates to:
  /// **'Правила и согласия'**
  String get rulesTitle;

  /// No description provided for @rulesGateTitle.
  ///
  /// In ru, this message translates to:
  /// **'Правила школы'**
  String get rulesGateTitle;

  /// No description provided for @rulesUpdated.
  ///
  /// In ru, this message translates to:
  /// **'Правила обновились'**
  String get rulesUpdated;

  /// No description provided for @rulesGateText.
  ///
  /// In ru, this message translates to:
  /// **'Чтобы продолжить, прочитайте и примите правила (версия {version}, действуют с {date}).'**
  String rulesGateText(String version, String date);

  /// No description provided for @rulesAgree.
  ///
  /// In ru, this message translates to:
  /// **'Я прочитал(а) и согласен(на) с правилами'**
  String get rulesAgree;

  /// No description provided for @rulesAccept.
  ///
  /// In ru, this message translates to:
  /// **'Принять правила'**
  String get rulesAccept;

  /// No description provided for @rulesAcceptedV.
  ///
  /// In ru, this message translates to:
  /// **'Вы приняли правила, версия {version}'**
  String rulesAcceptedV(String version);

  /// No description provided for @tabRules.
  ///
  /// In ru, this message translates to:
  /// **'Правила'**
  String get tabRules;

  /// No description provided for @tabRecording.
  ///
  /// In ru, this message translates to:
  /// **'Запись уроков'**
  String get tabRecording;

  /// No description provided for @recordingParent.
  ///
  /// In ru, this message translates to:
  /// **'Уроки могут записываться для контроля качества. Подпишите согласие за каждого ребёнка.'**
  String get recordingParent;

  /// No description provided for @recordingSelf.
  ///
  /// In ru, this message translates to:
  /// **'Уроки могут записываться для контроля качества. Подтвердите согласие.'**
  String get recordingSelf;

  /// No description provided for @recordingHint.
  ///
  /// In ru, this message translates to:
  /// **'Согласие можно отозвать в любой момент'**
  String get recordingHint;

  /// No description provided for @notSigned.
  ///
  /// In ru, this message translates to:
  /// **'Не подписано'**
  String get notSigned;

  /// No description provided for @signedAt.
  ///
  /// In ru, this message translates to:
  /// **'Подписано {date}'**
  String signedAt(String date);

  /// No description provided for @sign.
  ///
  /// In ru, this message translates to:
  /// **'Подписать'**
  String get sign;

  /// No description provided for @revoke.
  ///
  /// In ru, this message translates to:
  /// **'Отозвать'**
  String get revoke;

  /// No description provided for @revokeTitle.
  ///
  /// In ru, this message translates to:
  /// **'Отозвать согласие?'**
  String get revokeTitle;

  /// No description provided for @revokeText.
  ///
  /// In ru, this message translates to:
  /// **'Школа перестанет записывать уроки с участием ребёнка.'**
  String get revokeText;

  /// No description provided for @revoked.
  ///
  /// In ru, this message translates to:
  /// **'Согласие отозвано'**
  String get revoked;

  /// No description provided for @consentSaved.
  ///
  /// In ru, this message translates to:
  /// **'Сохранено'**
  String get consentSaved;

  /// No description provided for @docNotPublished.
  ///
  /// In ru, this message translates to:
  /// **'Документ ещё не опубликован'**
  String get docNotPublished;

  /// No description provided for @docVersion.
  ///
  /// In ru, this message translates to:
  /// **'Версия {version} · действует с {date}'**
  String docVersion(String version, String date);

  /// No description provided for @docUpcoming.
  ///
  /// In ru, this message translates to:
  /// **'С {date} вступит версия {version}'**
  String docUpcoming(String version, String date);

  /// No description provided for @fAll.
  ///
  /// In ru, this message translates to:
  /// **'Все'**
  String get fAll;

  /// No description provided for @fAttendance.
  ///
  /// In ru, this message translates to:
  /// **'Посещения'**
  String get fAttendance;

  /// No description provided for @fPayments.
  ///
  /// In ru, this message translates to:
  /// **'Оплаты'**
  String get fPayments;

  /// No description provided for @fStudy.
  ///
  /// In ru, this message translates to:
  /// **'Учёба'**
  String get fStudy;

  /// No description provided for @noNotifications.
  ///
  /// In ru, this message translates to:
  /// **'Уведомлений нет'**
  String get noNotifications;

  /// No description provided for @language.
  ///
  /// In ru, this message translates to:
  /// **'Язык'**
  String get language;

  /// No description provided for @theme.
  ///
  /// In ru, this message translates to:
  /// **'Тема'**
  String get theme;

  /// No description provided for @themeLight.
  ///
  /// In ru, this message translates to:
  /// **'Светлая'**
  String get themeLight;

  /// No description provided for @themeDark.
  ///
  /// In ru, this message translates to:
  /// **'Тёмная'**
  String get themeDark;

  /// No description provided for @themeSystem.
  ///
  /// In ru, this message translates to:
  /// **'Авто'**
  String get themeSystem;

  /// No description provided for @security.
  ///
  /// In ru, this message translates to:
  /// **'Безопасность'**
  String get security;

  /// No description provided for @securitySub.
  ///
  /// In ru, this message translates to:
  /// **'PIN-код, биометрия, устройства'**
  String get securitySub;

  /// No description provided for @logout.
  ///
  /// In ru, this message translates to:
  /// **'Выйти'**
  String get logout;

  /// No description provided for @logoutTitle.
  ///
  /// In ru, this message translates to:
  /// **'Выйти из аккаунта?'**
  String get logoutTitle;

  /// No description provided for @logoutText.
  ///
  /// In ru, this message translates to:
  /// **'Чтобы войти снова, понадобится код из WhatsApp.'**
  String get logoutText;

  /// No description provided for @devices.
  ///
  /// In ru, this message translates to:
  /// **'Устройства'**
  String get devices;

  /// No description provided for @devicesHint.
  ///
  /// In ru, this message translates to:
  /// **'Если видите незнакомое устройство — завершите его сеанс и напишите менеджеру.'**
  String get devicesHint;

  /// No description provided for @thisDevice.
  ///
  /// In ru, this message translates to:
  /// **'Это устройство'**
  String get thisDevice;

  /// No description provided for @endSession.
  ///
  /// In ru, this message translates to:
  /// **'Завершить'**
  String get endSession;

  /// No description provided for @endOthers.
  ///
  /// In ru, this message translates to:
  /// **'Завершить другие сеансы'**
  String get endOthers;

  /// No description provided for @endOthersText.
  ///
  /// In ru, this message translates to:
  /// **'На всех других устройствах придётся войти заново.'**
  String get endOthersText;

  /// No description provided for @unknownDevice.
  ///
  /// In ru, this message translates to:
  /// **'Неизвестное устройство'**
  String get unknownDevice;

  /// No description provided for @appDevice.
  ///
  /// In ru, this message translates to:
  /// **'Приложение One English'**
  String get appDevice;

  /// No description provided for @web.
  ///
  /// In ru, this message translates to:
  /// **'Браузер'**
  String get web;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['kk', 'ru'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'kk':
      return AppLocalizationsKk();
    case 'ru':
      return AppLocalizationsRu();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
