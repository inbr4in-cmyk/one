// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Russian (`ru`).
class AppLocalizationsRu extends AppLocalizations {
  AppLocalizationsRu([String locale = 'ru']) : super(locale);

  @override
  String get back => 'Назад';

  @override
  String get navHome => 'Главная';

  @override
  String get navSchedule => 'Расписание';

  @override
  String get navHomework => 'Задания';

  @override
  String get navChats => 'Чаты';

  @override
  String get navCoins => 'Коины';

  @override
  String get navPayments => 'Оплата';

  @override
  String get navNotifications => 'Уведомления';

  @override
  String get navProfile => 'Профиль';

  @override
  String get retry => 'Повторить';

  @override
  String get cancel => 'Отмена';

  @override
  String get loading => 'Загрузка…';

  @override
  String get send => 'Отправить';

  @override
  String get search => 'Поиск';

  @override
  String get call => 'Позвонить';

  @override
  String get copy => 'Скопировать';

  @override
  String get copied => 'Скопировано';

  @override
  String get remove => 'Убрать';

  @override
  String get understood => 'Понятно';

  @override
  String get notNow => 'Не сейчас';

  @override
  String get selected => 'Выбран';

  @override
  String get today => 'Сегодня';

  @override
  String get yesterday => 'Вчера';

  @override
  String get you => 'Вы';

  @override
  String get school => 'Школа';

  @override
  String branchName(String name) {
    return 'Филиал $name';
  }

  @override
  String get branchShort => 'Ваш филиал';

  @override
  String get errGeneric => 'Что-то пошло не так. Попробуйте ещё раз.';

  @override
  String get errNetwork => 'Нет связи с сервером. Проверьте интернет.';

  @override
  String get nothingFound => 'Ничего не найдено';

  @override
  String get wdMon => 'Пн';

  @override
  String get wdTue => 'Вт';

  @override
  String get wdWed => 'Ср';

  @override
  String get wdThu => 'Чт';

  @override
  String get wdFri => 'Пт';

  @override
  String get wdSat => 'Сб';

  @override
  String get wdSun => 'Вс';

  @override
  String get roleParent => 'Родитель';

  @override
  String get roleTeacher => 'Преподаватель';

  @override
  String get roleManager => 'Менеджер';

  @override
  String get roleAdmin => 'Администратор';

  @override
  String get roleStaff => 'Школа';

  @override
  String get splashFoot => 'Школа английского языка · Шымкент';

  @override
  String get offlineTitle => 'Нет подключения';

  @override
  String get offlineText =>
      'Не удалось связаться с сервером. Проверьте интернет и попробуйте снова.';

  @override
  String get loginTitle => 'Вход';

  @override
  String get loginText =>
      'Введите номер телефона, который вы оставили в школе.';

  @override
  String get phoneLabel => 'Номер телефона';

  @override
  String get phoneInvalid => 'Введите номер полностью: +7 и 10 цифр';

  @override
  String get codeChannel => 'Куда прислать код';

  @override
  String get waFast => 'Быстрее всего';

  @override
  String get smsSoon => 'Скоро';

  @override
  String get getCode => 'Получить код';

  @override
  String noNumber(String phone) {
    return 'Номера нет в школе? Напишите нам в WhatsApp $phone';
  }

  @override
  String get staffRejected =>
      'Это приложение для учеников и родителей. Сотрудники работают в веб-кабинете.';

  @override
  String get codeTitle => 'Код из WhatsApp';

  @override
  String get codeSent => 'Мы отправили 6-значный код на номер';

  @override
  String get codeWrong => 'Неверный код';

  @override
  String get codeAgain => 'Отправить код ещё раз';

  @override
  String codeAgainIn(String time) {
    return 'Отправить ещё раз через $time';
  }

  @override
  String get codeResent => 'Код отправлен ещё раз';

  @override
  String get pinCreate => 'Придумайте PIN-код';

  @override
  String get pinCreateText =>
      '4 цифры для быстрого входа. Без него вход — по коду из WhatsApp.';

  @override
  String get pinRepeat => 'Повторите PIN-код';

  @override
  String get pinMismatch => 'Коды не совпадают. Попробуйте ещё раз.';

  @override
  String get pinWeak =>
      'Слишком простой код. Не используйте 1111, 1234 или год рождения.';

  @override
  String get pinHint => 'Код хранится только на этом телефоне';

  @override
  String pinEnter(String name) {
    return 'Здравствуйте, $name';
  }

  @override
  String pinWrong(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: 'Неверный код. Осталось $n попытки',
      many: 'Неверный код. Осталось $n попыток',
      few: 'Неверный код. Осталось $n попытки',
      one: 'Неверный код. Осталась $n попытка',
    );
    return '$_temp0';
  }

  @override
  String get pinForgot => 'Забыли код? Войти по номеру';

  @override
  String get pinTooMany =>
      'Слишком много попыток. Войдите заново по номеру телефона.';

  @override
  String get pinChange => 'Сменить PIN-код';

  @override
  String get pinSet => 'Установить PIN-код';

  @override
  String get pinChanged => 'PIN-код сохранён';

  @override
  String get pinOff => 'Отключить PIN-код';

  @override
  String get pinOffTitle => 'Отключить PIN-код?';

  @override
  String get pinOffText =>
      'Приложение будет открываться без кода. Вход по биометрии тоже отключится.';

  @override
  String get erase => 'Стереть';

  @override
  String get bioTitleIos => 'Входить по Face ID?';

  @override
  String get bioTitleAndroid => 'Входить по отпечатку?';

  @override
  String get bioText =>
      'Это быстрее, чем PIN-код. Код остаётся запасным способом.';

  @override
  String get bioEnableIos => 'Включить Face ID';

  @override
  String get bioEnableAndroid => 'Включить отпечаток';

  @override
  String get bioUse => 'Войти по биометрии';

  @override
  String get bioReason => 'Подтвердите вход в One English';

  @override
  String get bioToggleIos => 'Вход по Face ID';

  @override
  String get bioToggleAndroid => 'Вход по отпечатку';

  @override
  String get autolock => 'Автоблокировка';

  @override
  String get autolockText => 'Спрашивать PIN-код после выхода из приложения';

  @override
  String get autolockNow => 'Сразу';

  @override
  String minutesN(int n) {
    return '$n мин';
  }

  @override
  String get blockedTitle => 'Доступ приостановлен';

  @override
  String get blockedText =>
      'Занятия закончились, а оплата не поступила. После оплаты всё откроется автоматически.';

  @override
  String get blockedShort => 'Доступ приостановлен';

  @override
  String get toPayments => 'К оплате';

  @override
  String get noChildren => 'Детей пока нет';

  @override
  String get noChildrenText =>
      'Школа ещё не привязала ребёнка к вашему номеру. Напишите менеджеру.';

  @override
  String helloStudent(String name) {
    return 'Привет, $name!';
  }

  @override
  String helloParent(String name) {
    return 'Здравствуйте, $name';
  }

  @override
  String get nextLesson => 'Следующий урок';

  @override
  String get lessonNow => 'Идёт сейчас';

  @override
  String inDays(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: 'через $n дня',
      many: 'через $n дней',
      few: 'через $n дня',
      one: 'через $n день',
    );
    return '$_temp0';
  }

  @override
  String inHoursMinutes(int h, int m) {
    return 'через $h ч $m мин';
  }

  @override
  String inMinutes(int m) {
    return 'через $m мин';
  }

  @override
  String room(String room) {
    return 'Кабинет $room';
  }

  @override
  String get individualLesson => 'Индивидуальное занятие';

  @override
  String get lessonsLeft => 'Осталось уроков';

  @override
  String ofN(int n) {
    return 'из $n';
  }

  @override
  String heldN(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: 'Проведено $n урока',
      many: 'Проведено $n уроков',
      few: 'Проведено $n урока',
      one: 'Проведён $n урок',
    );
    return '$_temp0';
  }

  @override
  String perWeek(int n) {
    return '+$n за неделю';
  }

  @override
  String get myBalance => 'Мои коины';

  @override
  String get hwToday => 'Задания на сегодня';

  @override
  String dueAt(String time) {
    return 'до $time';
  }

  @override
  String hwCheckedGrade(int grade) {
    return 'Проверено · $grade';
  }

  @override
  String hwTodayAt(String time) {
    return 'Сегодня до $time';
  }

  @override
  String get allTasks => 'Все задания';

  @override
  String get attendanceMonth => 'Посещаемость за месяц';

  @override
  String presentOf(int a, int b) {
    return 'Был на $a из $b';
  }

  @override
  String get debtTitle => 'Есть долг';

  @override
  String debtText(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: 'Долг $n урока — пополните баланс',
      many: 'Долг $n уроков — пополните баланс',
      few: 'Долг $n урока — пополните баланс',
      one: 'Долг $n урок — пополните баланс',
    );
    return '$_temp0';
  }

  @override
  String lowTitle(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: 'Осталось $n урока',
      many: 'Осталось $n уроков',
      few: 'Осталось $n урока',
      one: 'Остался $n урок',
      zero: 'Уроки закончились',
    );
    return '$_temp0';
  }

  @override
  String get lowText => 'Пополните баланс, чтобы не прерывать занятия';

  @override
  String get consentTitle => 'Согласие на запись уроков';

  @override
  String get consentText => 'Подпишите согласие в разделе «Правила»';

  @override
  String get avgGrade => 'Средняя оценка';

  @override
  String avgFor(String month, int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: '$month · $n оценки',
      many: '$month · $n оценок',
      few: '$month · $n оценки',
      one: '$month · $n оценка',
    );
    return '$_temp0';
  }

  @override
  String attendanceOf(String month) {
    return 'Посещаемость · $month';
  }

  @override
  String nOfM(int a, int b) {
    return '$a из $b';
  }

  @override
  String get stPresent => 'Был';

  @override
  String get stLate => 'Опоздал';

  @override
  String get stAbsent => 'Не был';

  @override
  String get stExcused => 'Уважительная';

  @override
  String get stAhead => 'Впереди';

  @override
  String get progress => 'Успеваемость';

  @override
  String get myProgress => 'Мои успехи';

  @override
  String get monthLessons => 'Уроков';

  @override
  String get monthPresent => 'Посетил';

  @override
  String get monthRate => 'Посещаемость';

  @override
  String get thisWeek => 'Эта неделя';

  @override
  String get prevWeek => 'Прошлая неделя';

  @override
  String get nextWeek => 'Следующая неделя';

  @override
  String get noLessons => 'Уроков нет';

  @override
  String get noLessonsWeek => 'На этой неделе уроков нет';

  @override
  String get cancelled => 'Отменён';

  @override
  String cancelledOn(String day, String time) {
    return 'Урок $day в $time отменён';
  }

  @override
  String get held => 'Проведён';

  @override
  String get teacherComment => 'Комментарий преподавателя';

  @override
  String get rateLesson => 'Оцените урок';

  @override
  String get yourRating => 'Ваша оценка';

  @override
  String get rated => 'Спасибо за оценку!';

  @override
  String starsN(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: '$n звезды',
      many: '$n звёзд',
      few: '$n звезды',
      one: '$n звезда',
    );
    return '$_temp0';
  }

  @override
  String get lessonGrades => 'Оценки за урок';

  @override
  String get hwActive => 'Активные';

  @override
  String hwActiveN(int n) {
    return 'Активные · $n';
  }

  @override
  String get hwReview => 'На проверке';

  @override
  String get hwChecked => 'Проверено';

  @override
  String get hwAssigned => 'Задано';

  @override
  String get hwOverdue => 'Просрочено';

  @override
  String get hwSubmitted => 'Сдано';

  @override
  String get hwNotSubmitted => 'Ответ не был сдан';

  @override
  String get hwNone => 'Здесь пока пусто';

  @override
  String get hwNoneActive => 'Все задания сделаны';

  @override
  String get hwNotFound => 'Задание не найдено';

  @override
  String get hwTask => 'Задание';

  @override
  String dueFull(String date) {
    return 'Сдать до $date';
  }

  @override
  String get myAnswer => 'Мой ответ';

  @override
  String get hwAnswerHint => 'Напишите ответ…';

  @override
  String get hwOneFile => 'Можно приложить один файл: фото, голос или документ';

  @override
  String get hwFile => 'Файл';

  @override
  String get hwSubmit => 'Сдать задание';

  @override
  String get hwSent => 'Задание отправлено на проверку';

  @override
  String get hwRedo => 'Переделать';

  @override
  String get hwNoAnswer => 'Напишите ответ или приложите файл';

  @override
  String get hwNoAnswerParent => 'Ученик ещё не сдал это задание';

  @override
  String get photo => 'Фото';

  @override
  String get camera => 'Камера';

  @override
  String get gallery => 'Галерея';

  @override
  String get voice => 'Голос';

  @override
  String get file => 'Файл';

  @override
  String get stop => 'Стоп';

  @override
  String get play => 'Слушать';

  @override
  String get pause => 'Пауза';

  @override
  String get uploading => 'Загружаем файл…';

  @override
  String get micDenied =>
      'Нет доступа к микрофону. Разрешите его в настройках телефона.';

  @override
  String recording(String time) {
    return 'Запись $time';
  }

  @override
  String get recordVoice => 'Записать голосовое';

  @override
  String get progressAndGrades => 'Успеваемость и оценки';

  @override
  String get level => 'Уровень';

  @override
  String get average => 'Средняя';

  @override
  String get noMarks => 'Оценок пока нет';

  @override
  String get noTests => 'Тестов пока не было';

  @override
  String get attendanceHistory => 'История посещений';

  @override
  String get debt => 'Долг';

  @override
  String get notCharged => 'Не списан';

  @override
  String debtLessonsN(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: '$n урока в долг',
      many: '$n уроков в долг',
      few: '$n урока в долг',
      one: '$n урок в долг',
    );
    return '$_temp0';
  }

  @override
  String pricePer(String price) {
    return '$price за урок';
  }

  @override
  String get needPayment => 'Нужна оплата';

  @override
  String get howToPay => 'Как оплатить';

  @override
  String get payHowText =>
      'Оплатить можно в филиале наличными, картой или переводом. Онлайн-оплата в приложении появится позже.';

  @override
  String get onlineSoon => 'Онлайн-оплата скоро появится';

  @override
  String payFor(String name) {
    return 'Оплата за $name';
  }

  @override
  String callBranch(String name) {
    return 'Позвонить в филиал $name';
  }

  @override
  String get writeManager => 'Написать менеджеру';

  @override
  String lessonsN(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: '$n урока',
      many: '$n уроков',
      few: '$n урока',
      one: '$n урок',
    );
    return '$_temp0';
  }

  @override
  String onBalance(String sum) {
    return 'На балансе $sum';
  }

  @override
  String get history => 'История';

  @override
  String get noPayments => 'Оплат пока нет';

  @override
  String refunded(String sum) {
    return 'Возврат $sum';
  }

  @override
  String payCategory(String c) {
    String _temp0 = intl.Intl.selectLogic(c, {
      'course': 'Курс',
      'book': 'Учебник',
      'other': 'Оплата',
    });
    return '$_temp0';
  }

  @override
  String get payCash => 'Наличные';

  @override
  String get payCard => 'Карта';

  @override
  String get payTransfer => 'Перевод';

  @override
  String get bookPurchase => 'Покупка учебника';

  @override
  String get myBooks => 'Учебники';

  @override
  String get noBooks => 'Учебников пока нет';

  @override
  String get noBooksText => 'Здесь появятся учебники, купленные в школе';

  @override
  String booksLevel(String level) {
    return 'Уровень $level';
  }

  @override
  String get chat => 'Чат';

  @override
  String get noChats => 'Чатов пока нет';

  @override
  String get noChatsText =>
      'Напишите преподавателю или менеджеру — нажмите «Новый чат»';

  @override
  String get newChat => 'Новый чат';

  @override
  String get searchPeople => 'Поиск по имени';

  @override
  String get contactsHint =>
      'Можно написать преподавателям своих групп и менеджерам филиала';

  @override
  String get noContacts => 'Некому написать';

  @override
  String membersN(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: '$n участника',
      many: '$n участников',
      few: '$n участника',
      one: '$n участник',
    );
    return '$_temp0';
  }

  @override
  String get chatNotice =>
      'Переписка сохраняется в школе. Не отправляйте пароли и номера карт.';

  @override
  String get chatRulesTitle => 'Правила чата';

  @override
  String get chatRule1 =>
      'Общайтесь вежливо — переписку видит администрация школы.';

  @override
  String get chatRule2 =>
      'Ученикам нельзя обмениваться номерами телефонов с преподавателями.';

  @override
  String get chatRule3 =>
      'Если что-то не так — нажмите на сообщение и выберите «Пожаловаться».';

  @override
  String get noMessages => 'Сообщений пока нет';

  @override
  String get firstMessage => 'Напишите первое сообщение';

  @override
  String get message => 'Сообщение';

  @override
  String get attach => 'Прикрепить';

  @override
  String get pinned => 'Закреплённое';

  @override
  String pinnedN(int n) {
    return 'Закреплённые · $n';
  }

  @override
  String get messageHidden => 'Сообщение скрыто';

  @override
  String get hideMessage => 'Скрыть';

  @override
  String get hideTitle => 'Скрыть сообщение?';

  @override
  String get hideText => 'Сообщение исчезнет у всех участников чата.';

  @override
  String get report => 'Пожаловаться';

  @override
  String get reportWhy => 'Что не так с сообщением?';

  @override
  String get reportHint => 'Жалобу рассмотрит администрация школы';

  @override
  String get reasonInsult => 'Грубость или оскорбление';

  @override
  String get reasonSpam => 'Спам или реклама';

  @override
  String get reasonPersonal => 'Просят личные контакты';

  @override
  String get reasonOther => 'Другое';

  @override
  String reportSubject(String chat) {
    return 'Жалоба на сообщение в чате «$chat»';
  }

  @override
  String reportBody(
    String reason,
    String author,
    String at,
    String text,
    int id,
  ) {
    return 'Причина: $reason\nАвтор: $author\nВремя: $at\nСообщение: $text\nID сообщения: $id';
  }

  @override
  String reportSent(String date) {
    return 'Жалоба отправлена. Ответ до $date';
  }

  @override
  String get phoneBlockedTitle => 'Номер телефона в сообщении';

  @override
  String get phoneBlockedText =>
      'Ученикам нельзя отправлять номера телефонов в чатах школы. Уберите номер, чтобы отправить.';

  @override
  String get phoneShort => 'Уберите номер телефона';

  @override
  String get removeNumber => 'Убрать номер';

  @override
  String get shop => 'Магазин';

  @override
  String get rating => 'Рейтинг';

  @override
  String get orders => 'Мои заказы';

  @override
  String get exchange => 'Обменять';

  @override
  String get buyTitle => 'Обменять коины?';

  @override
  String buyText(String item, String price) {
    return '«$item» за $price коинов. Забрать можно у администратора филиала.';
  }

  @override
  String ordered(String item) {
    return 'Заказ «$item» оформлен';
  }

  @override
  String needMore(String n) {
    return 'Не хватает $n';
  }

  @override
  String get outOfStock => 'Нет в наличии';

  @override
  String get shopEmpty => 'Магазин пока пуст';

  @override
  String openOrders(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: '$n заказа ждут выдачи',
      many: '$n заказов ждут выдачи',
      few: '$n заказа ждут выдачи',
      one: '$n заказ ждёт выдачи',
    );
    return '$_temp0';
  }

  @override
  String groupN(String name) {
    return 'Группа $name';
  }

  @override
  String get noRating => 'Рейтинг пока пуст';

  @override
  String get noCoinHistory => 'Начислений пока нет';

  @override
  String get coinAward => 'Начисление';

  @override
  String coinOrder(String item) {
    return 'Обмен: $item';
  }

  @override
  String get coinOrderCancelled => 'Возврат за отменённый заказ';

  @override
  String coinsN(int n) {
    return '$n коинов';
  }

  @override
  String get noOrders => 'Заказов пока нет';

  @override
  String get orderPlaced => 'Оформлен';

  @override
  String get orderPlacedHint => 'Администратор подготовит подарок';

  @override
  String get orderReady => 'Готов к выдаче';

  @override
  String get orderReadyHint => 'Заберите у администратора филиала';

  @override
  String get orderIssued => 'Выдан';

  @override
  String get orderCancelled => 'Заказ отменён, коины вернулись';

  @override
  String get orderCancelledShort => 'Отменён';

  @override
  String get pickUp => 'Забрать';

  @override
  String get cancelOrder => 'Отменить заказ';

  @override
  String get cancelOrderTitle => 'Отменить заказ?';

  @override
  String cancelOrderText(String item, int coins) {
    return '«$item» — $coins коинов вернутся на баланс.';
  }

  @override
  String get trioLeft => 'уроков';

  @override
  String get trioCoins => 'коинов';

  @override
  String get trioStars => 'звёзд';

  @override
  String get feedback => 'Жалобы и предложения';

  @override
  String get feedbackSubtitle =>
      'Напишите, что можно улучшить. Ответим в течение 3 рабочих дней.';

  @override
  String get feedbackNew => 'Новое обращение';

  @override
  String get subject => 'Тема';

  @override
  String get subjectHint => 'Коротко о сути';

  @override
  String get subjectRequired => 'Укажите тему (от 3 символов)';

  @override
  String get complaintBody => 'Подробности';

  @override
  String get complaintBodyHint => 'Что произошло, когда и с кем';

  @override
  String get bodyRequired => 'Опишите подробнее (от 10 символов)';

  @override
  String get against => 'О преподавателе';

  @override
  String get againstHint =>
      'Если обращение о преподавателе — выберите его, оно уйдёт руководству, а не ему';

  @override
  String get nobody => 'Не о конкретном человеке';

  @override
  String teacherOf(String name) {
    return 'Преподаватель $name';
  }

  @override
  String get feedbackNote => 'Обращение увидят только руководители школы.';

  @override
  String complaintSent(String date) {
    return 'Обращение отправлено. Ответ до $date';
  }

  @override
  String get feedbackHistory => 'Мои обращения';

  @override
  String get feedbackEmpty => 'Обращений пока нет';

  @override
  String get feedbackEmptyText =>
      'Здесь появятся ваши жалобы и предложения с ответами';

  @override
  String sentAt(String date) {
    return 'Отправлено $date';
  }

  @override
  String dueAnswer(String date) {
    return 'ответ до $date';
  }

  @override
  String get answer => 'Ответ школы';

  @override
  String get appeal => 'Не согласен с ответом';

  @override
  String get appealTitle => 'Обжаловать ответ?';

  @override
  String get appealText => 'Обращение передадут операционному директору.';

  @override
  String get appealed => 'Передано операционному директору';

  @override
  String get cNew => 'Новое';

  @override
  String get cAcknowledged => 'Принято';

  @override
  String get cInvestigating => 'Разбираемся';

  @override
  String get cAnswered => 'Есть ответ';

  @override
  String get cAppealed => 'Обжаловано';

  @override
  String get cClosed => 'Закрыто';

  @override
  String get rulesTitle => 'Правила и согласия';

  @override
  String get rulesGateTitle => 'Правила школы';

  @override
  String get rulesUpdated => 'Правила обновились';

  @override
  String rulesGateText(String version, String date) {
    return 'Чтобы продолжить, прочитайте и примите правила (версия $version, действуют с $date).';
  }

  @override
  String get rulesAgree => 'Я прочитал(а) и согласен(на) с правилами';

  @override
  String get rulesAccept => 'Принять правила';

  @override
  String rulesAcceptedV(String version) {
    return 'Вы приняли правила, версия $version';
  }

  @override
  String get tabRules => 'Правила';

  @override
  String get tabRecording => 'Запись уроков';

  @override
  String get recordingParent =>
      'Уроки могут записываться для контроля качества. Подпишите согласие за каждого ребёнка.';

  @override
  String get recordingSelf =>
      'Уроки могут записываться для контроля качества. Подтвердите согласие.';

  @override
  String get recordingHint => 'Согласие можно отозвать в любой момент';

  @override
  String get notSigned => 'Не подписано';

  @override
  String signedAt(String date) {
    return 'Подписано $date';
  }

  @override
  String get sign => 'Подписать';

  @override
  String get revoke => 'Отозвать';

  @override
  String get revokeTitle => 'Отозвать согласие?';

  @override
  String get revokeText =>
      'Школа перестанет записывать уроки с участием ребёнка.';

  @override
  String get revoked => 'Согласие отозвано';

  @override
  String get consentSaved => 'Сохранено';

  @override
  String get docNotPublished => 'Документ ещё не опубликован';

  @override
  String docVersion(String version, String date) {
    return 'Версия $version · действует с $date';
  }

  @override
  String docUpcoming(String version, String date) {
    return 'С $date вступит версия $version';
  }

  @override
  String get fAll => 'Все';

  @override
  String get fAttendance => 'Посещения';

  @override
  String get fPayments => 'Оплаты';

  @override
  String get fStudy => 'Учёба';

  @override
  String get noNotifications => 'Уведомлений нет';

  @override
  String get language => 'Язык';

  @override
  String get theme => 'Тема';

  @override
  String get themeLight => 'Светлая';

  @override
  String get themeDark => 'Тёмная';

  @override
  String get themeSystem => 'Авто';

  @override
  String get security => 'Безопасность';

  @override
  String get securitySub => 'PIN-код, биометрия, устройства';

  @override
  String get logout => 'Выйти';

  @override
  String get logoutTitle => 'Выйти из аккаунта?';

  @override
  String get logoutText => 'Чтобы войти снова, понадобится код из WhatsApp.';

  @override
  String get devices => 'Устройства';

  @override
  String get devicesHint =>
      'Если видите незнакомое устройство — завершите его сеанс и напишите менеджеру.';

  @override
  String get thisDevice => 'Это устройство';

  @override
  String get endSession => 'Завершить';

  @override
  String get endOthers => 'Завершить другие сеансы';

  @override
  String get endOthersText =>
      'На всех других устройствах придётся войти заново.';

  @override
  String get unknownDevice => 'Неизвестное устройство';

  @override
  String get appDevice => 'Приложение One English';

  @override
  String get web => 'Браузер';
}
