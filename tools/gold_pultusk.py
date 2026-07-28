"""Already-verified Pułtusk P1 supplement (seven death acts; no acquisition)."""

from tools.gold_values import observed_state, original, unclear

SOURCE = r"E:\DNA\Helene_Research\Pultusk_Fond84_Goldsztejn.md"
FOND = "84"


def act(record_id, year, act_no, locator, facts):
    return {
        "record_id": record_id,
        "town": "Pułtusk",
        "fond": FOND,
        "year": year,
        "act_type": "death",
        "act_no": act_no,
        "language": "ru",
        "source_note": SOURCE,
        "source_locator": locator,
        "source_author": "Fork-Pultusk research sessions",
        "artifact_path": None,
        "facts": facts,
    }


ACT_SPECS = [
    act(
        "pultusk-1877-death-13",
        1877,
        13,
        "Session 2 §2",
        {
            "principal": {
                "name": original("Sura Goldsztejn", "Сура Гольдштейнъ"),
                "age": 34,
                "sex": "female",
                "residence": "Pułtusk",
            },
            "father": {"name": original("Szlema", "Шлемы")},
            "mother": {"name": original("Nemi", "Неми")},
            "spouse": {
                "name": unclear(
                    "Mirka Lejb Goldsztejn",
                    "Mortka Lejb Goldsztejn",
                    "Moshka Lejb Goldsztejn",
                    original_script="Мирка(?) Лейба Гольдштейна",
                ),
                "occupation": "merchant",
                "residence": "Pułtusk",
                "sex": "male",
            },
            "declarants": [{"name": "Abram Cukman", "age": 56, "occupation": "szkolnik"}],
            "deceased_left_behind": unclear(
                "widower Mirka Lejb Goldsztejn",
                "widower Mortka Lejb Goldsztejn",
                "widower Moshka Lejb Goldsztejn",
                original_script="овдовѣвшаго мужа Мирка(?) Лейба Гольдштейна",
            ),
        },
    ),
    act(
        "pultusk-1878-death-11",
        1878,
        11,
        "§2 death act 11/1878",
        {
            "registration_date": {
                "gregorian": "1878-05-24",
                "julian": "1878-05-12",
                "time": "10:00",
            },
            "principal": {
                "name": original("Ruchla Goldsztejn", "Рухля Гольдштейнъ"),
                "age": original(48, "сорока восьми лѣтъ"),
                "sex": "female",
                "residence": "Pułtusk",
            },
            "father": {"name": original("Josek", "Юска")},
            "mother": {"name": original("Fajga", "Файги")},
            "spouse": {
                "name": original("Szmul Josek Goldsztejn", "Шмуля Иоска Гольдштейна"),
                "occupation": original("merchant", "торговца"),
                "residence": "Pułtusk",
                "sex": "male",
            },
            "declarants": [
                {
                    "name": "Boruch Rozenblum",
                    "age": 48,
                    "occupation": "merchant",
                    "residence": "Pułtusk",
                },
                {
                    "name": "Abram Cinkman",
                    "age": 57,
                    "occupation": "szkolnik",
                    "residence": "Pułtusk",
                },
            ],
            "deceased_left_behind": original(
                "widower Szmul Josek Goldsztejn, merchant",
                "оставивъ послѣ себя овдовѣвшаго мужа Шмуля Иоска Гольдштейна, торговца",
            ),
        },
    ),
    act(
        "pultusk-1885-death-10",
        1885,
        10,
        "§2 death act 10/1885",
        {
            "registration_date": {
                "gregorian": "1885-02-13",
                "julian": "1885-02-01",
                "time": "10:00",
            },
            "principal": {
                "name": original("Fryda Goldsztejn", "Фрейда Гольдштейнъ"),
                "age": original(1, "одного года"),
                "sex": "female",
                "residence": "Pułtusk",
            },
            "father": {"name": original("Szmul Goldsztejn", "Шмуля")},
            "mother": {
                "name": original("Sura Goldsztejn", "Суры"),
                "maiden_name": original("Łopławicz", "Лоплавичъ"),
            },
            "declarants": [
                {
                    "name": unclear("Berusz Zalowicz Rudziński?"),
                    "age": 54,
                    "occupation": "merchant",
                },
                {"name": "Abram Szmilowicz Cukman", "age": 64, "occupation": "szkolnik"},
            ],
        },
    ),
    act(
        "pultusk-1886-death-33",
        1886,
        33,
        "Session 2 §1",
        {
            "registration_date": {
                "gregorian": "1886-06-02",
                "julian": "1886-05-21",
                "time": "15:00",
            },
            "principal": {
                "name": original("Eliszia Goldsztejn", "Элишія Гольдштейнъ"),
                "age": original(60, "шестидесяти лѣтъ"),
                "occupation": original("merchant", "торговецъ"),
                "residence": "Pułtusk",
                "sex": "male",
            },
            "father": {"name": original("Jankiel", "Янкеля")},
            "mother": {
                "name": original("Chaja", "Хаи"),
                "maiden_name": original("Szaulowa", "Шауловой"),
            },
            "spouse": {
                "name": original("Sura Goldsztejn", "Суру"),
                "maiden_name": original("Wajnsztok", "Вайнштокъ"),
                "sex": "female",
                "marital_status": "widow",
            },
            "declarants": [
                {
                    "name": "Boruch Rozenblum",
                    "age": 55,
                    "occupation": "merchant",
                    "residence": "Pułtusk",
                },
                {
                    "name": "Abram Cukman",
                    "age": 65,
                    "occupation": "szkolnik",
                    "residence": "Pułtusk",
                },
            ],
            "deceased_left_behind": original(
                "widow Sura née Wajnsztok", "Оставивъ послѣ себя вдову Суру, урожденную Вайнштокъ"
            ),
        },
    ),
    act(
        "pultusk-1890-death-12",
        1890,
        12,
        "Session 3 §1",
        {
            "registration_date": {
                "gregorian": "1890-02-09",
                "julian": "1890-01-28",
                "time": "16:00",
            },
            "principal": {
                "name": original("Laja Goldsztejn", "Лая Гольдштейнъ"),
                "age": original(66, "шестидесяти шести лѣтъ"),
                "residence": observed_state("ILLEGIBLE"),
                "sex": "female",
            },
            "father": {"name": original("Chaim Pejsach", "Хаима")},
            "mother": {
                "name": original("Wirka Pejsach", "Вирки"),
                "maiden_name": unclear("S—duszka", "Sendushka?", original_script="С…душка"),
            },
            "spouse": {
                "name": original("Moszek Goldsztejn", "Мошка Гольдштейна"),
                "occupation": original("laborer", "работника"),
                "sex": "male",
            },
            "declarants": [
                {"name": "Boruch Rozenblum", "age": 59, "occupation": "merchant"},
                {"name": "Abram Cukman", "age": 69, "occupation": "szkolnik"},
            ],
            "deceased_left_behind": original(
                "widower Moszek Goldsztejn, laborer", "овдовѣвшаго мужа Мошка Гольдштейна работника"
            ),
        },
    ),
    act(
        "pultusk-1890-death-43",
        1890,
        43,
        "Session 3 §2",
        {
            "event_date": {"time": "15:00", "date": None},
            "principal": {
                "name": original("Ruchla Goldsztejn", "Рухля Гольдштейнъ"),
                "age": original(55, "пятидесяти пяти лѣтъ"),
                "residence": "Pułtusk",
                "sex": "female",
            },
            "father": {"name": original("Szaul Wagman", "Шауля")},
            "mother": {"name": original("Etka Wagman", "Этки")},
            "spouse": {
                "name": original("Srul Nisim Goldsztejn", "Срула Нисима Гольдштейна"),
                "occupation": original("merchant", "торговца"),
                "sex": "male",
            },
            "declarants": [
                {"name": "Boruch Rozenblum", "age": 59},
                {"name": "Abram Cukman", "age": 69},
            ],
            "deceased_left_behind": original(
                "widower Srul Nisim Goldsztejn, merchant",
                "овдовѣвшаго мужа Срула Нисима Гольдштейна, торговца",
            ),
        },
    ),
    act(
        "pultusk-1890-death-53",
        1890,
        53,
        "Session 3 §3",
        {
            "principal": {
                "name": original("Abram Szmul Goldsztejn", "Абрамъ Шмуль Гольдштейнъ"),
                "age": original(61, "шестидесяти одного года"),
                "occupation": original("householder", "домовладѣлецъ"),
                "residence": "Pułtusk",
                "sex": "male",
            },
            "father": {"name": original("Jankiel Goldsztejn", "Янкеля Гольдштейна")},
            "mother": {
                "name": original("Zosia Goldsztejn", "Зоси"),
                "maiden_name": original("Eliaszew", "Еліашевъ"),
            },
            "spouse": {
                "name": original("Ruchla Goldsztejn", "Рухлю"),
                "maiden_name": original("Fersztenberg", "Ферштенбергъ"),
                "sex": "female",
                "marital_status": "widow",
            },
            "deceased_left_behind": original(
                "widow Ruchla née Fersztenberg", "овдовѣвшую жену Рухлю, урожденную Ферштенбергъ"
            ),
        },
    ),
]
