/** The public privacy policy (owner, 27.11.2026): needed for the App Store, Google Play and Meta. Three languages on one page. */
export type PrivacyLang = 'ru' | 'kk' | 'en'
export interface PrivacyDoc { title: string; updated: string; intro: string; sections: { h: string; p?: string[]; ul?: string[] }[] }

export const PRIVACY_UPDATED = '2026-11-27'
export const PRIVACY_CONTACT = { site: 'english.inbrain.kz', instagram: '1eng.kz' }

export const PRIVACY: Record<PrivacyLang, PrivacyDoc> = {
  ru: {
    title: 'Политика конфиденциальности',
    updated: 'Действует с 27 ноября 2026 года',
    intro: 'Эта политика описывает, какие данные собирает школа английского языка One English (г. Шымкент, Казахстан) на сайте english.inbrain.kz и в мобильном приложении One English, зачем они нужны и как вы можете ими управлять. Мы обрабатываем персональные данные по Закону Республики Казахстан «О персональных данных и их защите».',
    sections: [
      { h: '1. Какие данные мы собираем', ul: [
        'Данные ученика: имя и фамилия, дата рождения, номер телефона, филиал, группа, уровень, номер и дата договора.',
        'Данные родителя или законного представителя: имя, номер телефона, кем приходится ученику.',
        'Учёба: расписание, посещаемость, домашние задания, оценки, результаты тестов, включая видеоответы в устной части теста.',
        'Оплаты: суммы, даты и способ оплаты, остаток уроков. Данные банковских карт мы не получаем и не храним.',
        'Сообщения: переписка в чатах приложения, а также сообщения, которые вы сами пишете школе в Instagram и WhatsApp.',
        'Ответы в анкетах и оценках уроков, жалобы и обращения.',
        'Технические данные: тип устройства, язык, адрес для push-уведомлений, IP-адрес и время входа для защиты учётной записи.',
      ] },
      { h: '2. Зачем мы их используем', ul: [
        'Чтобы организовать обучение: расписание, посещаемость, задания, тесты, связь с учителем и администратором.',
        'Чтобы вести учёт оплат и остатка уроков.',
        'Чтобы отправлять уведомления об уроках, оплатах и изменениях в расписании.',
        'Чтобы отвечать на ваши обращения и улучшать качество уроков.',
        'Чтобы защищать учётные записи и расследовать нарушения.',
      ], p: ['Мы не продаём данные и не используем их для рекламы третьих лиц.'] },
      { h: '3. Кто видит данные', p: [
        'Данные видят только сотрудники школы и только в объёме, который нужен им для работы: учитель видит своих учеников, администратор видит свой филиал. Родитель видит данные только своего ребёнка. Ученики и чужие родители не могут писать друг другу. Действия сотрудников записываются в журнал.',
      ] },
      { h: '4. Кому мы передаём данные', ul: [
        'Meta (Instagram и WhatsApp): когда вы пишете школе в этих сервисах или получаете от нас сообщение в WhatsApp.',
        'Google Firebase и Apple: чтобы доставить push-уведомление на ваше устройство.',
        'Государственным органам: только по требованию закона Республики Казахстан.',
      ], p: ['Другим лицам данные не передаются.'] },
      { h: '5. Как мы храним и защищаем данные', p: [
        'Данные хранятся на сервере, которым управляет школа. Соединение с сайтом и приложением зашифровано (HTTPS), пароли хранятся в виде хеша, доступ сотрудников разграничен по ролям. Данные хранятся, пока ученик учится в школе, а после этого столько, сколько требует закон для договоров и бухгалтерского учёта.',
      ] },
      { h: '6. Дети', p: [
        'Учётную запись ребёнка создаёт школа по договору с родителем или законным представителем. Согласие на обработку данных ребёнка даёт родитель. Родитель может посмотреть данные ребёнка в приложении и попросить их исправить или удалить.',
      ] },
      { h: '7. Ваши права', ul: [
        'Узнать, какие данные о вас есть у школы, и получить их копию.',
        'Исправить неточные данные.',
        'Отозвать согласие и попросить удалить учётную запись и данные. Мы удалим их, кроме тех, которые обязаны хранить по закону.',
      ], p: ['Чтобы воспользоваться правами, напишите администратору своего филиала в чате приложения или школе в Instagram @1eng.kz. Мы ответим в течение 15 рабочих дней.'] },
      { h: '8. Изменения политики', p: ['Если политика изменится, новая версия появится на этой странице, а о важных изменениях мы сообщим в приложении.'] },
    ],
  },
  kk: {
    title: 'Құпиялылық саясаты',
    updated: '2026 жылғы 27 қарашадан бастап қолданылады',
    intro: 'Бұл саясат One English ағылшын тілі мектебі (Шымкент қ., Қазақстан) english.inbrain.kz сайтында және One English мобильді қосымшасында қандай деректерді жинайтынын, олардың не үшін қажет екенін және оларды қалай басқара алатыныңызды сипаттайды. Біз дербес деректерді Қазақстан Республикасының «Дербес деректер және оларды қорғау туралы» Заңына сәйкес өңдейміз.',
    sections: [
      { h: '1. Біз қандай деректерді жинаймыз', ul: [
        'Оқушының деректері: аты-жөні, туған күні, телефон нөмірі, филиалы, тобы, деңгейі, шарттың нөмірі мен күні.',
        'Ата-ананың немесе заңды өкілдің деректері: аты-жөні, телефон нөмірі, оқушыға кім болатыны.',
        'Оқу: сабақ кестесі, қатысу, үй тапсырмалары, бағалар, тест нәтижелері, соның ішінде ауызша бөлімдегі бейнежауаптар.',
        'Төлемдер: сомасы, күні және төлем тәсілі, қалған сабақ саны. Банк картасының деректерін біз алмаймыз және сақтамаймыз.',
        'Хабарламалар: қосымшадағы чаттар, сондай-ақ мектепке Instagram және WhatsApp арқылы өзіңіз жазған хабарламалар.',
        'Сауалнама жауаптары, сабақ бағалары, шағымдар мен өтініштер.',
        'Техникалық деректер: құрылғы түрі, тіл, push-хабарлама мекенжайы, тіркелгіні қорғау үшін IP-мекенжай мен кіру уақыты.',
      ] },
      { h: '2. Оларды не үшін қолданамыз', ul: [
        'Оқуды ұйымдастыру үшін: кесте, қатысу, тапсырмалар, тесттер, мұғаліммен және әкімшімен байланыс.',
        'Төлемдер мен қалған сабақтардың есебін жүргізу үшін.',
        'Сабақтар, төлемдер және кесте өзгерістері туралы хабарлама жіберу үшін.',
        'Өтініштеріңізге жауап беру және сабақ сапасын жақсарту үшін.',
        'Тіркелгілерді қорғау және бұзушылықтарды тексеру үшін.',
      ], p: ['Біз деректерді сатпаймыз және үшінші тұлғалардың жарнамасы үшін қолданбаймыз.'] },
      { h: '3. Деректерді кім көреді', p: [
        'Деректерді тек мектеп қызметкерлері және тек жұмысына қажет көлемде көреді: мұғалім өз оқушыларын, әкімші өз филиалын көреді. Ата-ана тек өз баласының деректерін көреді. Оқушылар мен басқа ата-аналар бір-біріне жаза алмайды. Қызметкерлердің әрекеттері журналға жазылады.',
      ] },
      { h: '4. Деректерді кімге береміз', ul: [
        'Meta (Instagram және WhatsApp): осы қызметтерде мектепке жазғанда немесе бізден WhatsApp арқылы хабарлама алғанда.',
        'Google Firebase және Apple: құрылғыңызға push-хабарлама жеткізу үшін.',
        'Мемлекеттік органдарға: тек Қазақстан Республикасы заңының талабы бойынша.',
      ], p: ['Басқа тұлғаларға деректер берілмейді.'] },
      { h: '5. Деректерді қалай сақтаймыз және қорғаймыз', p: [
        'Деректер мектеп басқаратын серверде сақталады. Сайтпен және қосымшамен байланыс шифрланған (HTTPS), құпиясөздер хеш түрінде сақталады, қызметкерлердің қолжетімділігі рөлдер бойынша шектелген. Деректер оқушы мектепте оқып жүрген кезде, ал одан кейін шарттар мен бухгалтерлік есеп үшін заң талап ететін мерзімде сақталады.',
      ] },
      { h: '6. Балалар', p: [
        'Баланың тіркелгісін мектеп ата-анамен немесе заңды өкілмен жасалған шарт бойынша ашады. Баланың деректерін өңдеуге келісімді ата-ана береді. Ата-ана баланың деректерін қосымшадан көре алады және оларды түзетуді немесе жоюды сұрай алады.',
      ] },
      { h: '7. Сіздің құқықтарыңыз', ul: [
        'Мектепте сіз туралы қандай деректер бар екенін білу және олардың көшірмесін алу.',
        'Дәл емес деректерді түзету.',
        'Келісімді қайтарып алу және тіркелгі мен деректерді жоюды сұрау. Заң бойынша сақтауға міндетті деректерден басқасын жоямыз.',
      ], p: ['Құқықтарыңызды пайдалану үшін қосымшадағы чатта өз филиалыңыздың әкімшісіне немесе мектептің Instagram парақшасына @1eng.kz жазыңыз. Біз 15 жұмыс күні ішінде жауап береміз.'] },
      { h: '8. Саясаттың өзгеруі', p: ['Саясат өзгерсе, жаңа нұсқасы осы бетте жарияланады, ал маңызды өзгерістер туралы қосымшада хабарлаймыз.'] },
    ],
  },
  en: {
    title: 'Privacy Policy',
    updated: 'Effective from 27 November 2026',
    intro: 'This policy explains what data the One English language school (Shymkent, Kazakhstan) collects on the website english.inbrain.kz and in the One English mobile app, why it is needed and how you can control it. We process personal data under the Law of the Republic of Kazakhstan "On Personal Data and Their Protection".',
    sections: [
      { h: '1. Data we collect', ul: [
        'Student data: first and last name, date of birth, phone number, branch, group, level, contract number and date.',
        'Parent or legal guardian data: name, phone number, relation to the student.',
        'Learning: timetable, attendance, homework, grades, test results, including video answers in the speaking part of a test.',
        'Payments: amounts, dates and payment method, lessons left. We do not receive or store bank card details.',
        'Messages: chats inside the app, and messages you send to the school on Instagram and WhatsApp.',
        'Answers to questionnaires and lesson ratings, complaints and requests.',
        'Technical data: device type, language, push notification address, IP address and sign-in time to protect the account.',
      ] },
      { h: '2. Why we use it', ul: [
        'To run the lessons: timetable, attendance, homework, tests, contact with the teacher and the administrator.',
        'To keep track of payments and lessons left.',
        'To send notifications about lessons, payments and timetable changes.',
        'To answer your requests and improve the quality of lessons.',
        'To protect accounts and investigate violations.',
      ], p: ['We do not sell data and do not use it for third-party advertising.'] },
      { h: '3. Who can see the data', p: [
        'Only school staff can see the data, and only as much as their job needs: a teacher sees their own students, an administrator sees their own branch. A parent sees only their own child\'s data. Students and other families cannot message each other. Staff actions are recorded in a log.',
      ] },
      { h: '4. Who we share data with', ul: [
        'Meta (Instagram and WhatsApp): when you write to the school in these services or receive a WhatsApp message from us.',
        'Google Firebase and Apple: to deliver a push notification to your device.',
        'Government bodies: only when the law of the Republic of Kazakhstan requires it.',
      ], p: ['Data is not shared with anyone else.'] },
      { h: '5. How we store and protect data', p: [
        'Data is stored on a server managed by the school. The connection to the website and the app is encrypted (HTTPS), passwords are stored as hashes, and staff access is limited by role. Data is kept while the student studies at the school, and afterwards for as long as the law requires for contracts and accounting.',
      ] },
      { h: '6. Children', p: [
        'A child\'s account is created by the school under a contract with a parent or legal guardian. Consent to process a child\'s data is given by the parent. A parent can see the child\'s data in the app and ask to correct or delete it.',
      ] },
      { h: '7. Your rights', ul: [
        'To learn what data the school holds about you and get a copy of it.',
        'To correct inaccurate data.',
        'To withdraw consent and ask to delete the account and the data. We delete it, except for what the law obliges us to keep.',
      ], p: ['To use these rights, write to your branch administrator in the app chat or to the school on Instagram @1eng.kz. We answer within 15 working days.'] },
      { h: '8. Changes to this policy', p: ['If the policy changes, the new version appears on this page, and we announce important changes in the app.'] },
    ],
  },
}

/** /support: the «Support URL» the app stores ask for */
export const SUPPORT: Record<PrivacyLang, PrivacyDoc> = {
  ru: {
    title: 'Поддержка One English',
    updated: 'Приложение и сайт школы английского языка One English, г. Шымкент',
    intro: 'Здесь собраны ответы на частые вопросы о приложении и сайте english.inbrain.kz и способы связаться со школой.',
    sections: [
      { h: 'Как войти', p: ['Ученики и родители входят по номеру телефона, который записан в школе, и коду подтверждения. Если номер изменился или код не приходит, обратитесь к администратору своего филиала.'] },
      { h: 'Как связаться со школой', ul: ['В приложении: раздел «Чаты», чат с администратором или менеджером.', 'Instagram: @1eng.kz.', 'Лично: у администратора вашего филиала.'] },
      { h: 'Как удалить учётную запись и данные', p: ['Напишите администратору своего филиала в чате приложения или школе в Instagram @1eng.kz с просьбой удалить учётную запись. Мы удалим её и связанные данные, кроме тех, которые обязаны хранить по закону, и ответим в течение 15 рабочих дней.'] },
      { h: 'Документы', p: ['Политика конфиденциальности: english.inbrain.kz/privacy'] },
    ],
  },
  kk: {
    title: 'One English қолдау қызметі',
    updated: 'One English ағылшын тілі мектебінің қосымшасы мен сайты, Шымкент қ.',
    intro: 'Мұнда қосымша мен english.inbrain.kz сайты туралы жиі қойылатын сұрақтардың жауаптары және мектеппен байланысу тәсілдері жиналған.',
    sections: [
      { h: 'Қалай кіруге болады', p: ['Оқушылар мен ата-аналар мектепте тіркелген телефон нөмірі және растау коды арқылы кіреді. Нөмір өзгерсе немесе код келмесе, өз филиалыңыздың әкімшісіне хабарласыңыз.'] },
      { h: 'Мектеппен қалай байланысуға болады', ul: ['Қосымшада: «Чаттар» бөлімі, әкімшімен немесе менеджермен чат.', 'Instagram: @1eng.kz.', 'Өзіңіз келіп: филиал әкімшісіне.'] },
      { h: 'Тіркелгі мен деректерді қалай жоюға болады', p: ['Қосымшадағы чатта өз филиалыңыздың әкімшісіне немесе мектептің Instagram парақшасына @1eng.kz тіркелгіні жою туралы жазыңыз. Заң бойынша сақтауға міндетті деректерден басқасын жоямыз және 15 жұмыс күні ішінде жауап береміз.'] },
      { h: 'Құжаттар', p: ['Құпиялылық саясаты: english.inbrain.kz/privacy'] },
    ],
  },
  en: {
    title: 'One English Support',
    updated: 'The app and website of the One English language school, Shymkent',
    intro: 'Answers to common questions about the app and the website english.inbrain.kz, and ways to contact the school.',
    sections: [
      { h: 'How to sign in', p: ['Students and parents sign in with the phone number registered at the school and a confirmation code. If the number has changed or the code does not arrive, contact your branch administrator.'] },
      { h: 'How to contact the school', ul: ['In the app: the "Chats" section, a chat with the administrator or manager.', 'Instagram: @1eng.kz.', 'In person: at your branch administrator\'s desk.'] },
      { h: 'How to delete your account and data', p: ['Write to your branch administrator in the app chat or to the school on Instagram @1eng.kz and ask to delete the account. We delete it and the related data, except for what the law obliges us to keep, and answer within 15 working days.'] },
      { h: 'Documents', p: ['Privacy Policy: english.inbrain.kz/privacy'] },
    ],
  },
}
