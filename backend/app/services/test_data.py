"""Beginner Progress Test 2 as the school sent it (owner's files, 25.11.2026): the first staged test, loaded for the
staff's trial run. Twelve timed stages, 100 points; writing and speaking are checked by a person."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Level, Question, Test

TITLE = "Progress Test 2"


def _pick(text: str, options: list[str], right: int) -> dict:
    return {"kind": "single", "text": text, "options": options, "correct": [right]}


def _type(text: str, *accept: str) -> dict:
    return {"kind": "input", "text": text, "accept": list(accept)}


TF = ["True", "False"]
WORDS = ["vegetables", "relax", "dinner", "housework", "arrive", "water", "study", "wear", "sandwich", "morning"]
READING = (
    "Anna lives in a small house with her family and a black cat named Shadow. She is a student, and she goes to university "
    "from Monday to Friday.\n\n"
    "On Sundays, Anna does not have classes. She wakes up at 8:00 AM. First, she drinks a cup of warm tea and eats breakfast "
    "with her family. Then, she goes to the local park. Anna loves to walk in the park and read books under a big oak tree.\n\n"
    "In the afternoon, Anna meets her best friend, Marco. They go to a small Italian café near the park. Anna usually drinks a "
    "cappuccino and eats a slice of chocolate cake. Marco likes orange juice and pizza. They talk about their week and laugh a lot.\n\n"
    "In the evening, Anna goes home, watches a movie, and goes to bed early because Monday is a busy day."
)

# (stage, questions). Points: 1 per question unless set.
PARTS: list[tuple[dict, list[dict]]] = [
    ({"id": "g1", "section": "Grammar", "title": "Choose the correct option", "minutes": 8}, [
        _pick("She ___ English every day.", ["study", "studies"], 1),
        _pick("They ___ football on Sundays.", ["always play", "play always"], 0),
        _pick("___ you swim well?", ["Can", "Does"], 0),
        _pick("I don't like ___ horror movies.", ["watch", "watching"], 1),
        _pick("He ___ a book every month.", ["give me", "gives me", "give I", "gives I"], 1),
        _pick("How often ___ he go to the gym?", ["do", "does"], 1),
        _pick("We ___ hear the music; it is too quiet.", ["can", "can't"], 1),
        _pick("My brother loves ___ pasta.", ["cook", "cooking"], 1),
        _pick("___ they eat fish?", ["Do", "Does"], 0),
        _pick("I ___ late for work.", ["never am", "am never"], 1),
        _pick("She hates ___ the washing up.", ["do", "doing"], 1),
        _pick("___ she speak French?", ["Can", "Do"], 0),
        _pick("Tell ___ the truth.", ["he", "him"], 1),
        _pick("They ___ playing basketball.", ["like", "likes"], 0),
    ]),
    ({"id": "g2", "section": "Grammar", "title": "Put the words in the correct order to make questions", "minutes": 9,
      "hint": "Example: you / like / do / pizza / ? → Do you like pizza?"}, [
        _type("often / you / how / do / exercise / ?", "How often do you exercise?"),
        _type("can / speak / languages / you / what / ?", "What languages can you speak?"),
        _type("does / where / live / your / friend / ?", "Where does your friend live?"),
        _type("she / like / does / running / ?", "Does she like running?"),
        _type("help / you / can / me / ?", "Can you help me?"),
        _type("time / do / what / get up / they / ?", "What time do they get up?"),
        _type("she / does / why / hate / cooking / ?", "Why does she hate cooking?"),
        _type("is / it / what / time / ?", "What time is it?"),
        _type("music / you / listen / do / to / ?", "Do you listen to music?"),
    ]),
    ({"id": "g3", "section": "Grammar", "title": "Fill in the gaps with ONE word", "minutes": 5,
      "hint": "Use Present Simple, adverbs, pronouns, can/can't, or like/love/hate + -ing."}, [
        _type("I don't like horror movies. I ___ watching comedies.", "like", "love"),
        _type("Can you help ___ with this bag? It's heavy.", "me"),
        _type("She ___ goes to school by bus; she prefers walking.", "never"),
        _type("My dog ___ bark, but it can't talk.", "can"),
        _type("We hate ___ up early on Saturdays.", "waking", "getting"),
        _type("Does he like pizza? Yes, he loves ___.", "it"),
        _type("Where ___ she live?", "does"),
    ]),
    ({"id": "v1", "section": "Vocabulary", "title": "Choose the correct option", "minutes": 8}, [
        _pick("In the morning, I like to drink a cup of ___ with milk.", ["coffee", "bread", "meat"], 0),
        _pick("A ___ works in a hospital to help sick people.", ["doctor", "waiter", "teacher"], 0),
        _pick("We need to pack our ___ before going on holiday.", ["suitcase", "sunglasses", "ticket"], 0),
        _pick("My favorite hobby is ___ with blue and red colors.", ["painting", "soup", "rice"], 0),
        _pick("On Sundays, I usually ___ late, around 10:00 a.m.", ["get up", "go home", "go to bed"], 0),
        _pick("She wants to buy a ticket for a ___ to travel to London.", ["taxi", "train", "car"], 1),
        _pick("I love eating fresh ___, like apples and bananas.", ["fruit", "tea", "beer"], 0),
        _pick("My brother works as a ___ in a big high school.", ["teacher", "office", "hospital"], 0),
        _pick("For breakfast, I usually have ___ with cold milk.", ["cereal", "dinner", "lunch"], 0),
        _pick("Can you ___ the piano beautifully?", ["play", "wait", "walk"], 0),
        _pick("We are going to ___ a TV series tonight.", ["watch", "listen", "read"], 0),
        _pick("I want to ___ a car for our trip next week.", ["rent", "book", "wear"], 0),
        _pick("She is a ___ and writes articles for a newspaper.", ["journalist", "factory", "office"], 0),
        _pick("My father is ___ and looking for a new job.", ["unemployed", "hospital", "restaurant"], 0),
    ]),
    ({"id": "v2", "section": "Vocabulary", "title": "Fill in the gaps", "minutes": 8, "words": WORDS,
      "hint": "Use the words from the list. Each word can be used only once."}, [
        _type("I usually have a ___ with cheese for lunch.", "sandwich"),
        _type("My favorite ___ are potatoes and carrots.", "vegetables"),
        _type("In the ___, I always have a quick shower.", "morning"),
        _type("When I am tired, I like to ___ on the sofa.", "relax"),
        _type("We have ___ at home every evening.", "dinner"),
        _type("Do you ___ English at school or at home?", "study"),
        _type("When the weather is cold, I ___ a coat.", "wear"),
        _type("What time do you ___ at the hotel?", "arrive"),
        _type("I am thirsty, can I have a glass of ___?", "water"),
        _type("On Saturdays, my brother does the ___ at home.", "housework"),
    ]),
    ({"id": "v3", "section": "Vocabulary", "title": "Odd one out", "minutes": 5,
      "hint": "Find the word that doesn't belong in each group."}, [
        _pick("Which word doesn't belong?", ["January", "March", "Tuesday", "August", "September"], 2),
        _pick("Which word doesn't belong?", ["Water", "Coffee", "Tea", "Beer", "Sandwich"], 4),
        _pick("Which word doesn't belong?", ["Doctor", "Nurse", "Hospital", "Journalist", "Waiter"], 2),
        _pick("Which word doesn't belong?", ["Cycling", "Swimming", "Reading", "Running", "Potatoes"], 4),
        _pick("Which word doesn't belong?", ["Office", "School", "Factory", "Restaurant", "Suitcase"], 4),
        _pick("Which word doesn't belong?", ["Breakfast", "Lunch", "Dinner", "Shopping", "Morning"], 3),
    ]),
    ({"id": "r1", "section": "Reading", "title": "Questions (Multiple Choice)", "minutes": 5, "text_title": "Anna's Sunday", "text": READING}, [
        _pick("Where does Anna live?", ["In a big apartment", "In a small house", "At the university"], 1),
        _pick("What animal does Anna have?", ["A dog", "A white cat", "A black cat"], 2),
        _pick("What time does Anna wake up on Sunday?", ["At 7:00 AM", "At 8:00 AM", "At 9:00 AM"], 1),
        _pick("Where does Anna read books?", ["Under a big oak tree in the park", "In her bedroom", "In the library"], 0),
        _pick("What does Anna drink at the café?", ["Orange juice", "Warm tea", "Cappuccino"], 2),
        _pick("What does Marco like to eat at the café?", ["Chocolate cake", "Pizza", "Sandwiches"], 1),
    ]),
    ({"id": "r2", "section": "Reading", "title": "True or False?", "minutes": 3, "text_title": "Anna's Sunday", "text": READING}, [
        _pick("Anna goes to university on Sunday.", TF, 1),
        _pick("Anna's cat is named Shadow.", TF, 0),
        _pick("Anna meets her brother at the café.", TF, 1),
        _pick("Anna stays up late on Sunday night.", TF, 1),
    ]),
    ({"id": "w1", "section": "Writing", "title": "Writing", "minutes": 8, "hint": "Write about 20 words for each task."}, [
        {"kind": "text", "points": 4, "text": "Your Best Friend\nDescribe your best friend: what is their name, how old are they, what do "
                                              "they look like, and what do you like to do together?"},
        {"kind": "text", "points": 3, "text": "Your Favorite Day\nWhat is your favorite day of the week, why do you like it, and what do "
                                              "you usually do on this day?"},
        {"kind": "text", "points": 3, "text": "Your Hobby\nWhat is your favorite hobby, how often do you do it, and why do you enjoy it?"},
    ]),
    ({"id": "l1", "section": "Listening", "title": "Choose the best word to complete these sentences", "minutes": 3,
      "audio": "/media/tests/bpt2-listening-1.mp3"}, [
        _pick("Aurelia is asking about Hannah's ___.", ["boyfriend", "brother", "friend"], 1),
        _pick("Hannah's brother, Jem, has ___.", ["long, brown hair", "a girlfriend", "a twin sister"], 1),
        _pick("Hannah has ___.", ["one brother", "two brothers", "a brother and a sister"], 1),
        _pick("Alex and Jem ___.", ["look different", "look the same", "have the same hair but different eyes"], 1),
    ]),
    ({"id": "l2", "section": "Listening", "title": "Choose the best answer to complete these sentences", "minutes": 3,
      "audio": "/media/tests/bpt2-listening-2.mp3"}, [
        _pick("Ismael is ___.", ["OK, but a bit ill", "OK, but has a lot of homework", "OK, but a bit bored"], 1),
        _pick("'Light and dark' is a ___.", ["horror film", "science fiction film", "romantic comedy"], 0),
        _pick("The comedy film is about a ___.", ["family", "shop", "school"], 2),
        _pick("Jack hates ___.", ["horror films", "romantic films", "science fiction films"], 1),
        _pick("They decide to see a ___.", ["romcom", "horror film", "science fiction film"], 2),
        _pick("They decide to meet at ___.", ["7 o'clock", "half past seven", "8 o'clock"], 1),
    ]),
    ({"id": "s1", "section": "Speaking", "title": "Speaking", "minutes": 10, "seconds": 100,
      "hint": "Answer the questions using full sentences. Try to give as much detail as you can."}, [
        {"kind": "video", "points": 2, "text": "What do you do on a normal day?"},
        {"kind": "video", "points": 2, "text": "What is your favorite food and your favorite drink?"},
        {"kind": "video", "points": 2, "text": "How often do you go to the gym / watch TV / cook dinner?"},
        {"kind": "video", "points": 2, "text": "What two things can you do? What two things can't you do?"},
        {"kind": "video", "points": 2, "text": "What two things do you like doing? What two things do you hate doing?"},
    ]),
]


async def seed_bpt2(db: AsyncSession) -> dict:
    """Loads Beginner Progress Test 2 once. An existing test with this title on the level is left as it is."""
    level = await db.scalar(select(Level).where(func.lower(Level.name) == "beginner", Level.archived_at.is_(None)))
    if level is None:
        return {"created": False, "reason": "no level named Beginner"}
    if await db.scalar(select(Test.id).where(Test.level_id == level.id, Test.title == TITLE, Test.archived_at.is_(None))):
        return {"created": False, "reason": "already there"}
    t = Test(kind="progress", title=TITLE, level_id=level.id, max_score=100, time_limit_min=sum(p["minutes"] for p, _ in PARTS),
             is_published=True, scale=[], parts=[p for p, _ in PARTS])
    db.add(t)
    await db.flush()
    n = 0
    for p, qs in PARTS:
        for q in qs:
            n += 1
            db.add(Question(test_id=t.id, order=n, part=p["id"], kind=q["kind"], text=q["text"], options=q.get("options", []),
                            correct=q.get("correct", []), accept=q.get("accept"), points=q.get("points", 1)))
    await db.commit()
    return {"created": True, "test_id": t.id, "questions": n, "points": sum(q.get("points", 1) for _, qs in PARTS for q in qs)}
