import json
import math
import random
from collections import Counter
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Set, Tuple, TypeVar, Union

import requests

from rivoli.config import ECO_COUNTER_URL, get_twitter
from rivoli.exceptions import FailedRequestingEcoCounterError, PublishError
from rivoli.utils import parse_mdy

MAX_TWEET_LENGTH = 280


class DictionaryKey(Enum):
    HISTORICAL_TOTAL = 'HISTORICAL_TOTAL'
    YEAR_TOTAL = 'YEAR_TOTAL'
    MONTH_TOTAL = 'MONTH_TOTAL'
    FIRST = 'FIRST'
    SECOND = 'SECOND'
    THIRD = 'THIRD'
    ITH = 'ITH'
    FEMALE_BEST = 'FEMALE_BEST'
    MALE_BEST = 'MALE_BEST'
    MONDAY = 'MONDAY'
    TUESDAY = 'TUESDAY'
    WEDNESDAY = 'WEDNESDAY'
    THURSDAY = 'THURSDAY'
    FRIDAY = 'FRIDAY'
    SATURDAY = 'SATURDAY'
    SUNDAY = 'SUNDAY'
    SINCE_BEGINING = 'SINCE_BEGINING'
    SINCE_BEGINING_OF_YEAR = 'SINCE_BEGINING_OF_YEAR'
    SINCE_BEGINING_OF_MONTH = 'SINCE_BEGINING_OF_MONTH'
    DAY_OF_MONTH = 'DAY_OF_MONTH'
    DAY_OF_YEAR = 'DAY_OF_YEAR'
    DAY_OF_HISTORY = 'DAY_OF_HISTORY'
    MONTH_OF_YEAR = 'MONTH_OF_YEAR'
    MONTH_OF_HISTORY = 'MONTH_OF_HISTORY'
    YEAR_OF_HISTORY = 'YEAR_OF_HISTORY'
    YESTERDAY = 'YESTERDAY'
    TODAY = 'TODAY'


class DayOfWeek(Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

    def to_dictionary_key(self) -> DictionaryKey:
        return DictionaryKey(self.name)


class Language(Enum):
    FR = 'fr'
    EN = 'en'

    @staticmethod
    def values() -> Set:
        return {Language.FR, Language.EN}


class Dictionary:
    def __init__(self, key_to_language_to_sentence: Dict[DictionaryKey, Dict[Language, str]]) -> None:
        self.key_to_language_to_sentence: Dict[DictionaryKey, Dict[Language, str]] = key_to_language_to_sentence

    def __getitem__(self, key: DictionaryKey):
        return self.key_to_language_to_sentence[key]

    def to_json(self) -> Dict:
        return self.key_to_language_to_sentence

    @classmethod
    def from_json(cls, json_dictionary: Dict[str, Dict[str, str]]):
        is_ok, message = cls.check_json(json_dictionary)
        if not is_ok:
            raise ValueError(message)
        dict_ = {
            DictionaryKey(dict_key): {
                Language(language): sentence for language, sentence in language_to_sentence.items()
            }
            for dict_key, language_to_sentence in json_dictionary.items()
        }
        return cls(key_to_language_to_sentence=dict_)

    @staticmethod
    def check_json(json_dictionary: Dict[str, Dict[str, str]]) -> Tuple[bool, str]:
        if isinstance(json_dictionary, dict):
            return False, 'json_dictionary must be of type dict'
        return True, ''


class Publisher:
    def publish(self, message: str) -> None:
        raise NotImplementedError()

    def can_be_published(self, message: str) -> bool:
        raise NotImplementedError()


class TweetPublisher(Publisher):
    def publish(self, message: str) -> None:
        if not self.can_be_published(message):
            raise PublishError(f'Cannot publish tweet {message}.')
        twitter_api = get_twitter()
        twitter_api.update_status(message)

    def can_be_published(self, message: str) -> bool:
        return len(message) <= MAX_TWEET_LENGTH


class SlackPublisher(Publisher):
    def __init__(self, slack_url: str) -> None:
        self.slack_url: str = slack_url

    def publish(self, message: str) -> None:
        if not self.can_be_published(message):
            raise PublishError(f'Cannot publish message {message} to slack.')
        requests.post(url=self.slack_url, data=json.dumps({'text': message}))

    def can_be_published(self, message: str) -> bool:
        return True


class TimeRange:
    start_date: datetime

    def contains(self, date: datetime) -> bool:
        raise NotImplementedError()

    @staticmethod
    def check(date: datetime) -> None:
        raise NotImplementedError()

    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        raise NotImplementedError()


class MonthTimeRange(TimeRange):
    def __init__(self, start_date: datetime) -> None:
        self.check(start_date)
        self.start_date = start_date

    def contains(self, date: datetime) -> bool:
        return self.start_date.year == date.year and self.start_date.month == date.month

    @staticmethod
    def check(date: datetime) -> None:
        DayTimeRange.check(date)
        if date.day != 1:
            raise ValueError(f'Date {date} is not a month')

    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        raise NotImplementedError()


class YearTimeRange(TimeRange):
    def __init__(self, start_date: datetime) -> None:
        self.check(start_date)
        self.start_date = start_date

    def contains(self, date: datetime) -> bool:
        return self.start_date.year == date.year

    @staticmethod
    def check(date: datetime) -> None:
        MonthTimeRange.check(date)
        if date.month != 1:
            raise ValueError(f'Date {date} is not a year')

    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        raise NotImplementedError()


class CustomTimeRange(TimeRange):
    def __init__(self, start_date: datetime, end_date: datetime) -> None:
        self.start_date = start_date
        self.end_date = end_date

    def contains(self, date: datetime) -> bool:
        return self.start_date <= date < self.end_date

    @staticmethod
    def check(date: datetime) -> None:
        pass

    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        raise NotImplementedError()


class HistoricalTimeRange(CustomTimeRange):
    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        raise NotImplementedError()


class DayTimeRange(TimeRange):
    def __init__(self, start_date: datetime) -> None:
        self.check(start_date)
        self.start_date = start_date
        self.end_date = start_date + timedelta(days=1)

    def contains(self, date: datetime) -> bool:
        return self.start_date <= date < self.end_date

    def month_time_range(self) -> MonthTimeRange:
        first_day_of_month = datetime(year=self.start_date.year, month=self.start_date.month, day=1)
        return MonthTimeRange(first_day_of_month)

    def year_time_range(self) -> YearTimeRange:
        first_day_of_year = datetime(year=self.start_date.year, month=1, day=1)
        return YearTimeRange(first_day_of_year)

    def day_of_week(self) -> DayOfWeek:
        return DayOfWeek(self.start_date.weekday())

    def year(self) -> int:
        return self.start_date.year

    def month(self) -> int:
        return self.start_date.month

    @staticmethod
    def check(date: datetime) -> None:
        if date.hour != 0 or date.minute != 0 or date.second != 0:
            raise ValueError(f'Date {date} is not a day')

    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        if day_of_publication.date() == self.start_date.date():
            return dictionary[DictionaryKey.TODAY][language]
        if (day_of_publication - timedelta(days=1)).date() == self.start_date.date():
            return dictionary[DictionaryKey.YESTERDAY][language]
        raise NotImplementedError()


class HourTimeRange(TimeRange):
    def __init__(self, start_date: datetime) -> None:
        self.check(start_date)
        self.start_date = start_date
        self.end_date = start_date + timedelta(hours=1)

    def contains(self, date: datetime) -> bool:
        return self.start_date <= date < self.end_date

    def hour(self) -> int:
        return self.start_date.hour

    def day_of_week(self) -> DayOfWeek:
        return DayOfWeek(self.start_date.weekday())

    def day_time_range(self) -> DayTimeRange:
        day = datetime(year=self.start_date.year, month=self.start_date.month, day=self.start_date.day)
        return DayTimeRange(day)

    @staticmethod
    def check(date: datetime) -> None:
        if date.minute != 0 or date.second != 0:
            raise ValueError(f'Date {date} is not an hour')

    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        raise NotImplementedError()


class CountHistoryType(Enum):
    HOURLY_COUNT = 'HOURLY_COUNT'
    DAILY_COUNT = 'DAILY_COUNT'


TP = TypeVar('TP')


class DailyCountHistory:
    def __init__(self, day_to_count: Dict[DayTimeRange, int]) -> None:

        self.day_to_count: Dict[DayTimeRange, int] = day_to_count

        self.month_to_count: Dict[MonthTimeRange, int] = self._group_by_month(day_to_count)
        self.year_to_count: Dict[YearTimeRange, int] = self._group_by_year(day_to_count)
        self.total: int = sum(self.day_to_count.values())
        self.day_to_cumsum: Dict[DayTimeRange, int] = self._time_range_to_cumsum(day_to_count)
        self.month_to_cumsum: Dict[MonthTimeRange, int] = self._time_range_to_cumsum(self.month_to_count)
        self.day_of_week_to_best_count: Dict[DayOfWeek, int] = self._extract_day_of_week_to_best_count(day_to_count)

    @staticmethod
    def _group_by_month(day_to_count: Dict[DayTimeRange, int]) -> Dict[MonthTimeRange, int]:
        month_to_day_counts: Dict[MonthTimeRange, List[int]] = {}
        for day, count in day_to_count.items():
            month = day.month_time_range()
            month_to_day_counts[month] = month_to_day_counts.get(month, []) + [count]
        return {month: sum(counts) for month, counts in month_to_day_counts.items()}

    @staticmethod
    def _group_by_year(day_to_count: Dict[DayTimeRange, int]) -> Dict[YearTimeRange, int]:
        year_to_day_counts: Dict[YearTimeRange, List[int]] = {}
        for day, count in day_to_count.items():
            year = day.year_time_range()
            year_to_day_counts[year] = year_to_day_counts.get(year, []) + [count]
        return {year: sum(counts) for year, counts in year_to_day_counts.items()}

    @staticmethod
    def _time_range_to_cumsum(time_range_to_count: Dict[TP, int]) -> Dict[TP, int]:
        time_range_to_cumsum = {}
        cumsum = 0
        for key, count in sorted(time_range_to_count.items(), key=lambda x: x[0].start_date):
            cumsum += count
            time_range_to_cumsum[key] = cumsum
        return time_range_to_cumsum

    @staticmethod
    def _extract_day_of_week_to_best_count(day_to_count: Dict[DayTimeRange, int]) -> Dict[DayOfWeek, int]:
        day_of_week_to_day_counts: Dict[DayOfWeek, List[int]] = {}
        for day, count in day_to_count.items():
            day_of_week = day.day_of_week()
            day_of_week_to_day_counts[day_of_week] = day_of_week_to_day_counts.get(day_of_week, []) + [count]
        return {day_of_week: max(counts) for day_of_week, counts in day_of_week_to_day_counts.items()}


class HourlyCountHistory(DailyCountHistory):
    def __init__(self, hour_to_count: Dict[HourTimeRange, int]) -> None:
        day_to_count = self._group_by_day(hour_to_count)
        super().__init__(day_to_count)

        self.hour_to_count: Dict[HourTimeRange, int] = hour_to_count
        self.hour_to_cumsum: Dict[HourTimeRange, int] = self._time_range_to_cumsum(hour_to_count)
        self.hour_and_day_of_week_to_best_count: Dict[
            Tuple[int, DayOfWeek], int
        ] = self._extract_hour_and_day_of_week_to_best_count(hour_to_count)

    @staticmethod
    def _extract_hour_and_day_of_week_to_best_count(
        hour_to_count: Dict[HourTimeRange, int]
    ) -> Dict[Tuple[int, DayOfWeek], int]:
        hour_and_day_of_week_to_counts: Dict[Tuple[int, DayOfWeek], List[int]] = {}
        for hour, count in hour_to_count.items():
            key = (hour.hour(), hour.day_of_week())
            hour_and_day_of_week_to_counts[key] = hour_and_day_of_week_to_counts.get(key, []) + [count]
        return {key: max(counts) for key, counts in hour_and_day_of_week_to_counts.items()}

    @staticmethod
    def _group_by_day(hour_to_count: Dict[HourTimeRange, int]) -> Dict[DayTimeRange, int]:
        day_to_hour_counts: Dict[DayTimeRange, List[int]] = {}
        for hour, count in hour_to_count.items():
            day = hour.day_time_range()
            day_to_hour_counts[day] = day_to_hour_counts.get(day, []) + [count]
        return {day: sum(counts) for day, counts in day_to_hour_counts.items()}


class CountHistoryDownloader:
    def download_count_history(self) -> DailyCountHistory:
        raise NotImplementedError()


class EcoCounterDownloader(CountHistoryDownloader):
    def download_count_history(self) -> DailyCountHistory:
        answer = requests.post(ECO_COUNTER_URL)
        if answer.status_code != 200:
            json_answer = answer.json()
        else:
            raise FailedRequestingEcoCounterError(answer.content.decode())
        return self._format_answer(json_answer)

    @classmethod
    def _check_answer(cls, answer: List) -> Tuple[bool, str]:
        if not isinstance(answer, list):
            return False, f'Expected API answer type is list, received {type(answer)}'
        if not answer[0][0] != '09/02/2019':
            return False, f'Expected first day of data: 09/02/2019. Received {answer[0][0]}'
        pairs = answer[:-1]
        if {len(pair) for pair in pairs} != {2}:
            return (
                False,
                'Expecting a list of pairs, lengths received: {}'.format(
                    Counter([len(pair) for pair in pairs]).most_common()
                ),
            )
        return True, ''

    @classmethod
    def _format_pair(cls, pair: Tuple[str, str]) -> Tuple[DayTimeRange, int]:
        if len(pair) != 2:
            raise ValueError('Need a pair as argument, received {}'.format(pair))
        date = parse_mdy(pair[0])
        time_range = DayTimeRange(start_date=date)
        count = int(float(pair[1]))
        return time_range, count

    @staticmethod
    def _pad_answer(answer):
        return [['09/01/2019', '0']] + answer

    @classmethod
    def _format_answer(cls, answer: List[Tuple[str, str]]) -> DailyCountHistory:
        is_ok, message = cls._check_answer(answer)
        if not is_ok:
            raise ValueError(f'Cannot build count history from url answer, reason: {message}')
        padded_answer = cls._pad_answer(answer)
        day_to_count = dict([cls._format_pair(pair) for pair in padded_answer[:-1]])
        return DailyCountHistory(day_to_count=day_to_count)


def generate_mock_count_history(nb_days: int) -> DailyCountHistory:
    now = datetime.now()
    start_date = now - timedelta(days=nb_days)
    day_to_count = {DayTimeRange(start_date + timedelta(days=i)): random.randint(0, 100) for i in range(nb_days)}
    return DailyCountHistory(day_to_count)


class RelevantFactType(Enum):
    BEST_HOUR_IN_DAY = 'BEST_HOUR_IN_DAY'

    HISTORICAL_RANK_OF_BEST_HOUR = 'HISTORICAL_RANK_OF_BEST_HOUR'
    YEAR_RANK_OF_BEST_HOUR = 'YEAR_RANK_OF_BEST_HOUR'
    MONTH_RANK_OF_BEST_HOUR = 'MONTH_RANK_OF_BEST_HOUR'

    HISTORICAL_RANK_OF_DAY_OF_WEEK = 'HISTORICAL_RANK_OF_DAY_OF_WEEK'
    YEAR_RANK_OF_DAY_OF_WEEK = 'YEAR_RANK_OF_DAY_OF_WEEK'
    MONTH_RANK_OF_DAY_OF_WEEK = 'MONTH_RANK_OF_DAY_OF_WEEK'

    HISTORICAL_TOTAL = 'HISTORICAL_TOTAL'
    YEAR_TOTAL = 'YEAR_TOTAL'
    MONTH_TOTAL = 'MONTH_TOTAL'

    RANK_OF_YEAR_TOTAL = 'RANK_OF_YEAR_TOTAL'
    RANK_OF_MONTH_TOTAL = 'RANK_OF_MONTH_TOTAL'

    INTERESTING_HISTORICAL_TOTAL = 'INTERESTING_HISTORICAL_TOTAL'
    INTERESTING_YEAR_TOTAL = 'INTERESTING_YEAR_TOTAL'
    INTERESTING_MONTH_TOTAL = 'INTERESTING_MONTH_TOTAL'

    TOTAL_AVOIDED_CARBON = 'TOTAL_AVOIDED_CARBON'

    # multiple counter
    BEST_OTHER_COUNTER_DAY = 'BEST_OTHER_COUNTER_DAY'
    RANK_OF_COUNTER_AMONG_OTHER_COUNTERS = 'RANK_OF_COUNTER_AMONG_OTHER_COUNTERS'
    BEST_HOUR_AMONG_ALL_COUNTERS = 'BEST_HOUR_AMONG_ALL_COUNTERS'

    # compared to day qualifiers
    HISTORICAL_RANK_FOR_RAINY_DAYS = 'HISTORICAL_RANK_FOR_RAINY_DAYS'
    HISTORICAL_RANK_FOR_TEMPERATURE_OR_BELOW = 'HISTORICAL_RANK_FOR_TEMPERATURE_OR_BELOW'

    # machine learning
    PREDICTED_NUMBER_OF_CYCLISTS_FOR_THE_DAY = 'PREDICTED_NUMBER_OF_CYCLISTS_FOR_THE_DAY'


class RelevantFact:
    def __init__(self, target_range: TimeRange, priority: int) -> None:
        self.target_range: TimeRange = target_range
        self.priority: int = priority

    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        raise NotImplementedError()


def day_of_week_to_name(day_of_week: DayOfWeek, language: Language, dictionary: Dictionary):
    return dictionary[day_of_week.to_dictionary_key()][language]


def rank_to_ordinal(rank: int, language: Language, dictionary: Dictionary) -> str:
    if rank == 0:
        return dictionary[DictionaryKey.FIRST][language]
    if rank == 1:
        return dictionary[DictionaryKey.SECOND][language]
    if rank == 2:
        return dictionary[DictionaryKey.THIRD][language]
    return f'{rank}{dictionary[DictionaryKey.ITH][language]}'


class TotalRelevantFact(RelevantFact):
    def __init__(self, target_range: TimeRange, priority: int, total: int) -> None:
        super().__init__(target_range, priority)
        self.total: int = total

    @staticmethod
    def end_of_sentence(language: Language, dictionary: Dictionary) -> str:
        raise NotImplementedError()

    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        return f'{self.total} {self.end_of_sentence( language, dictionary)}.'


class HistoricalTotalRelevantFact(TotalRelevantFact):
    @staticmethod
    def end_of_sentence(language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.HISTORICAL_TOTAL][language]


class YearTotalRelevantFact(TotalRelevantFact):
    @staticmethod
    def end_of_sentence(language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.YEAR_TOTAL][language]


class MonthTotalRelevantFact(TotalRelevantFact):
    @staticmethod
    def end_of_sentence(language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.MONTH_TOTAL][language]


class RankOfTotalRelevantFact(RelevantFact):
    def __init__(self, target_range: TimeRange, priority: int, total: int, rank_of_total: int, ties: int) -> None:
        super().__init__(target_range, priority)
        self.total: int = total
        self.rank: int = rank_of_total
        self.ties: int = ties

    @staticmethod
    def _get_best(rank: int, language: Language, dictionary: Dictionary) -> str:
        raise NotImplementedError()

    @staticmethod
    def _get_rank_end_of_sentence(target_range: TimeRange, language: Language, dictionary: Dictionary) -> str:
        raise NotImplementedError()

    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        best = self._get_best(self.rank, language, dictionary)
        end_of_sentence = self._get_rank_end_of_sentence(self.target_range, language, dictionary)
        string_time_range = self.target_range.to_string(language, day_of_publication, dictionary)
        return f'{string_time_range}: {best} {end_of_sentence}'


class DayOfMonthRankOfTotalRelevantFact(RankOfTotalRelevantFact):
    @staticmethod
    def _get_best(rank: int, language: Language, dictionary: Dictionary) -> str:
        return get_male_best(rank, language, dictionary)

    @staticmethod
    def _get_rank_end_of_sentence(target_range: TimeRange, language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.DAY_OF_MONTH][language]


class DayOfYearRankOfTotalRelevantFact(RankOfTotalRelevantFact):
    @staticmethod
    def _get_best(rank: int, language: Language, dictionary: Dictionary) -> str:
        return get_male_best(rank, language, dictionary)

    @staticmethod
    def _get_rank_end_of_sentence(target_range: TimeRange, language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.DAY_OF_YEAR][language]


class DayOfHistoricalRankOfTotalRelevantFact(RankOfTotalRelevantFact):
    @staticmethod
    def _get_best(rank: int, language: Language, dictionary: Dictionary) -> str:
        return get_male_best(rank, language, dictionary)

    @staticmethod
    def _get_rank_end_of_sentence(target_range: TimeRange, language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.DAY_OF_HISTORY][language]


class MonthOfYearRankOfTotalRelevantFact(RankOfTotalRelevantFact):
    @staticmethod
    def _get_best(rank: int, language: Language, dictionary: Dictionary) -> str:
        return get_male_best(rank, language, dictionary)

    @staticmethod
    def _get_rank_end_of_sentence(target_range: TimeRange, language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.MONTH_OF_YEAR][language]


class MonthOfHistoryRankOfTotalRelevantFact(RankOfTotalRelevantFact):
    @staticmethod
    def _get_best(rank: int, language: Language, dictionary: Dictionary) -> str:
        return get_female_best(rank, language, dictionary)

    @staticmethod
    def _get_rank_end_of_sentence(target_range: TimeRange, language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.MONTH_OF_HISTORY][language]


class YearOfHistoryRankOfTotalRelevantFact(RankOfTotalRelevantFact):
    @staticmethod
    def _get_best(rank: int, language: Language, dictionary: Dictionary) -> str:
        return get_male_best(rank, language, dictionary)

    @staticmethod
    def _get_rank_end_of_sentence(target_range: TimeRange, language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.YEAR_OF_HISTORY][language]


def get_male_best(rank: int, language: Language, dictionary: Dictionary) -> str:
    ordinal = rank_to_ordinal(rank, language, dictionary)
    best = dictionary[DictionaryKey.MALE_BEST][language]
    ordinal_best = f'{ordinal} {best}' if rank else best
    return ordinal_best


def get_female_best(rank: int, language: Language, dictionary: Dictionary) -> str:
    ordinal = rank_to_ordinal(rank, language, dictionary)
    best = dictionary[DictionaryKey.FEMALE_BEST][language]
    ordinal_best = f'{ordinal} {best}' if rank else best
    return ordinal_best


def get_male_best_day_of_week_sentence(
    rank: int, day_of_week: DayOfWeek, language: Language, dictionary: Dictionary
) -> str:
    day_of_week_name = day_of_week_to_name(day_of_week, language, dictionary)
    return f'{get_male_best(rank, language, dictionary)} {day_of_week_name}'


class DayOfWeekRankRelevantFact(RelevantFact):
    def __init__(self, target_range: TimeRange, priority: int, day_of_week: DayOfWeek, rank: int, ties: int) -> None:
        super().__init__(target_range, priority)
        self.rank: int = rank
        self.ties: int = ties
        self.day_of_week: DayOfWeek = day_of_week

    @staticmethod
    def get_end_of_sentence(language: Language, dictionary: Dictionary) -> str:
        raise NotImplementedError()

    def to_string(self, language: Language, day_of_publication: datetime, dictionary: Dictionary) -> str:
        best_day_of_week_sentence = get_male_best_day_of_week_sentence(
            self.rank, self.day_of_week, language, dictionary
        )
        return f'{best_day_of_week_sentence} {self.get_end_of_sentence(language, dictionary)}.'


class HistoricalDayOfWeekRankRelevantFact(DayOfWeekRankRelevantFact):
    @staticmethod
    def get_end_of_sentence(language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.SINCE_BEGINING][language]


class YearDayOfWeekRankRelevantFact(DayOfWeekRankRelevantFact):
    @staticmethod
    def get_end_of_sentence(language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.SINCE_BEGINING_OF_YEAR][language]


class MonthDayOfWeekRankRelevantFact(DayOfWeekRankRelevantFact):
    @staticmethod
    def get_end_of_sentence(language: Language, dictionary: Dictionary) -> str:
        return dictionary[DictionaryKey.SINCE_BEGINING_OF_MONTH][language]


def extract_total_hourly(count_history: HourlyCountHistory, target_range: HourTimeRange) -> int:
    return count_history.hour_to_count[target_range]


def extract_total(count_history: DailyCountHistory, target_range: DayTimeRange) -> int:
    return count_history.day_to_count[target_range]


def human_rank_in_list(quantity: Union[float, int], list_: Union[List[float], List[int]]) -> Tuple[int, int]:
    sorted_list = [math.inf, *sorted(list_, reverse=True), -math.inf]
    left = 0
    right = len(sorted_list) - 1
    while left < right - 1:
        middle = (left + right) // 2
        if sorted_list[middle] > quantity:
            left = middle
        else:
            right = middle
    rank = right
    nb_ties = 0
    while right < len(sorted_list) and sorted_list[right] == quantity:
        nb_ties += 1
        right += 1
    return rank, nb_ties - 1


def extract_rank_and_ties_of_day_of_week(
    count_history: DailyCountHistory, target_range: DayTimeRange, same_year: bool = False
) -> Tuple[int, int]:
    count_with_same_dow = [
        count
        for day, count in count_history.day_to_count.items()
        if (day.day_of_week() == target_range.day_of_week() and (not same_year or day.year() == target_range.year()))
    ]
    count = count_history.day_to_count[target_range]
    return human_rank_in_list(count, count_with_same_dow)


def get_rank_of_day(
    count_history: DailyCountHistory,
    target_range: DayTimeRange,
    comparator: Callable[[DayTimeRange, DayTimeRange], bool],
) -> Tuple[int, int]:
    count = count_history.day_to_count[target_range]
    counts_in_same_year = [count for day, count in count_history.day_to_count.items() if comparator(day, target_range)]
    return human_rank_in_list(count, counts_in_same_year)


def share_year(range_1: DayTimeRange, range_2: DayTimeRange) -> bool:
    return range_1.year() == range_2.year()


def share_month(range_1: DayTimeRange, range_2: DayTimeRange) -> bool:
    return range_1.month() == range_2.month()


def get_rank_of_day_in_year(count_history: DailyCountHistory, target_range: DayTimeRange) -> Tuple[int, int]:
    return get_rank_of_day(count_history, target_range, share_year)


def get_rank_of_day_in_month(count_history: DailyCountHistory, target_range: DayTimeRange) -> Tuple[int, int]:
    return get_rank_of_day(count_history, target_range, share_month)


def extract_month_total(count_history: DailyCountHistory, target_range: DayTimeRange) -> int:
    return sum([count for day, count in count_history.day_to_count.items() if day.month() == target_range.month()])


def extract_relevant_facts(
    count_history: DailyCountHistory, among_range: TimeRange, target_range: DayTimeRange
) -> List[RelevantFact]:
    if not among_range.contains(target_range.start_date) or not among_range.contains(target_range.end_date):
        raise ValueError('Arg among_range must contain arg target_range')

    facts: List[RelevantFact] = []
    facts.append(HistoricalTotalRelevantFact(target_range, 0, extract_total(count_history, target_range)))
    facts.append(
        YearDayOfWeekRankRelevantFact(
            target_range,
            0,
            target_range.day_of_week(),
            *extract_rank_and_ties_of_day_of_week(count_history, target_range, same_year=True),
        )
    )
    facts.append(
        HistoricalDayOfWeekRankRelevantFact(
            target_range,
            0,
            target_range.day_of_week(),
            *extract_rank_and_ties_of_day_of_week(count_history, target_range),
        )
    )
    facts.append(
        DayOfYearRankOfTotalRelevantFact(
            target_range,
            0,
            count_history.day_to_count[target_range],
            *get_rank_of_day_in_year(count_history, target_range),
        )
    )
    facts.append(
        DayOfMonthRankOfTotalRelevantFact(
            target_range,
            0,
            count_history.day_to_count[target_range],
            *get_rank_of_day_in_month(count_history, target_range),
        )
    )
    facts.append(MonthTotalRelevantFact(target_range, 0, extract_month_total(count_history, target_range)))
    if isinstance(count_history, HourlyCountHistory):
        pass  # TODO
    return facts


def extract_highest_priority_relevant_facts(facts: List[RelevantFact]) -> List[RelevantFact]:
    max_priority = max([fact.priority for fact in facts])
    return [fact for fact in facts if fact.priority == max_priority]


def relevant_facts_to_string(
    relevant_facts: List[RelevantFact], language: Language, time_of_publication: datetime, dictionary: Dictionary
) -> str:
    if not relevant_facts:
        raise ValueError('Need at least one relevant fact')
    top_relevant_facts = extract_highest_priority_relevant_facts(relevant_facts)
    return random.choice(top_relevant_facts).to_string(language, time_of_publication, dictionary)