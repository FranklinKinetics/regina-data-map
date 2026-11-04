# Editing the words on the map

The opening message, the six story buttons and the "Did you know?" facts all live in one file: [`config/lab-content.json`](config/lab-content.json).

**To change them:** open the file on GitHub, press the pencil icon, edit the text, press **Commit changes**. That is all. GitHub rebuilds and publishes the map within a few minutes, and every downloaded copy of the map picks up the new words the next time someone opens it while online. Nobody needs a new download.

If you make a mistake (a typo in a `{number}`, a missing quote), the rebuild stops with a clear message in the **Actions** tab and the map stays as it was. A copy of the map that can't read the new words falls back to the words it already has.

## How it works

Write normal sentences. Wherever you want a live number, put its name in curly brackets, like `{permits_12m}`. The map fills it in from the data every time it opens, so the sentence never goes out of date.

> "In the 12 months to {latest} the City issued {permits_12m} building permits with {value_12m} of declared construction value."

becomes

> "In the 12 months to Oct 28, 2026 the City issued 2,833 building permits with $957.6 million of declared construction value."

* Text inside `[[double square brackets]]` only appears if every `{number}` inside it has a value. Use it for a sentence that might not apply (for example "the biggest project" when nothing matches).
* A **fact** that uses a number the map can't work out right now is left out instead of showing a gap.
* Keep each fact under about 300 characters, and each story caption under about 400.

## A story

```json
{
  "id": "suites",
  "title": "Suites and basements",
  "sub": "A quiet way Regina adds housing",
  "show": { "groups": ["suites"] },
  "caption": {
    "title": "{count} permits for secondary suites and basement developments",
    "body": "Not new buildings, but new places to live in existing ones. Most in {top_hood_count} ({top_hood_count_n})."
  }
}
```

* `id`: a short unique name using lowercase letters, numbers or dashes.
* `title` and `sub`: the button's two lines.
* `show` says what the map displays when the story is clicked. All parts are optional:
  * `groups`: which kinds of work to show. Any of `new-homes`, `new-multi`, `new-commercial`, `commercial-reno`, `suites`, `home-work`, `other`. Leave it out to show everything.
  * `min`: smallest declared value in dollars (`10000000` = $10 million and up).
  * `span`: only the last this-many days (`30` = last 30 days).
  * `events`: `true` shows rezonings and open applications instead of permits.
* `caption`: the box that appears on the map. The numbers inside are calculated from the permits the story is showing.

You can have 1 to 12 stories. They appear in the order they are written.

## Numbers for a story caption or the opening message

| Write this | You get |
|---|---|
| `{count}` | permits showing in the story |
| `{value}` / `{value_short}` | their total declared value, as "$957.6 million" / "$957.6M" |
| `{homes}` | new homes on those permits (laneway suites not counted) |
| `{median}` | the middle permit's value |
| `{share_of_year}` | those permits' share of the last 12 months' total value, as a whole number (add the % yourself) |
| `{top_hood_count}` and `{top_hood_count_n}` | neighbourhood with the most permits, and how many |
| `{top_hood_value}` and `{top_hood_value_amount}` | neighbourhood with the most declared value, and the amount |
| `{top_hood_homes}` and `{top_hood_homes_n}` | neighbourhood with the most new homes, and how many |
| `{biggest_what}`, `{biggest_address}`, `{biggest_hood}`, `{biggest_value}`, `{biggest_date}` | the single biggest permit showing: kind of work ("new commercial building"), address, neighbourhood, value, date |
| `{rezonings}`, `{applications}`, `{open_applications}` | rezonings spotted, City applications listed, and how many are open for public comment |
| `{latest}`, `{first_year}` | date of the newest permit, and the first year of data |

## Numbers for the "Did you know?" facts

These use the last 12 months ("12m"), everything since 2020 ("all"), or Regina-wide statistics.

| Write this | You get |
|---|---|
| `{latest}`, `{since}`, `{first_year}` | newest permit date, first permit date, first year |
| `{permits_12m}`, `{value_12m}`, `{homes_12m}`, `{per_day_12m}`, `{median_12m}` | permits, declared value, new homes, permits per working day, middle permit value |
| `{top_hood_count_12m}` and `{top_hood_count_12m_n}` | neighbourhood with the most permits, and how many |
| `{top_hood_homes_12m}` and `{top_hood_homes_12m_n}` | neighbourhood with the most new homes, and how many |
| `{biggest_what_12m}`, `{biggest_address_12m}`, `{biggest_hood_12m}`, `{biggest_value_12m}` | the biggest permit in the last 12 months |
| `{busiest_weekday}` and `{busiest_weekday_n}` | the weekday with the most permits, and how many |
| `{laneway_12m}` | backyard and laneway suites in the last 12 months |
| `{permits_all}`, `{value_all}` | all permits since 2020 and their total value |
| `{best_year}` and `{best_year_value}` | biggest complete year by declared value, and the amount |
| `{biggest_what_all}`, `{biggest_address_all}`, `{biggest_value_all}`, `{biggest_date_all}` | the biggest permit since 2020 |
| `{pop_first}`, `{pop_first_year}`, `{pop_last}`, `{pop_last_year}`, `{pop_growth_pct}` | Regina's population then and now, and the growth in per cent (Statistics Canada) |
| `{rent_last}`, `{rent_last_year}`, `{rent_first}`, `{rent_first_year}`, `{vacancy_last}` | average rent then and now, and the latest vacancy rate (CMHC) |
| `{rezonings}`, `{applications}`, `{open_applications}` | rezoning and application counts |
| `{tax_year}`, `{tax_res_100k}`, `{tax_com_100k}`, `{tax_com_more_pct}` | the latest tax year, the City + Library tax on each $100,000 of assessed value for homes and for commercial and industrial property, and how many per cent more the commercial rate is |

Need a number that isn't here (for example "permits in Harbour Landing")? Ask Claude to add it to the map's code. It is a small change, but it needs a new download of the map for the number to exist. Once it exists, you can use it in any fact from then on without another download.

## Adding next year's property tax rates

The tax chart reads `config/tax-rates.json`. Each spring, when City Council passes the year's Property Tax Bylaw, add one entry at the end of the list. Copy the last entry and change the numbers to match the bylaw (find it on openregina.ca by searching "Regina Property Tax Bylaw"):

* `year` and `bylaw` (for example 2027 and "2027-24"), and the link to the bylaw's page.
* `city` and `library`: the two mill rates in section 4(1).
* `bid_downtown` and `bid_warehouse`: the two business improvement district rates in section 4(2).
* `factors`: the mill rate factors in section 6 (residential, multi_family, commercial, golf).

Years must follow one after another with none missing. A typo, a missing year or a number that looks wrong stops the build with a message and the last good map stays live. The map sorts out which years are assessment resets by itself (the years the multipliers change).
