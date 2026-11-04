# 0029. ABC/XYZ of the articles bought

Status: accepted (plan day 28)

## Context

A buyer wants to know which articles carry the money (ABC) and which are ordered steadily enough to plan for (XYZ). The order history has what is needed:
the purchase orders, the items of their requests and the unit prices of the offers behind them.

## Decisions

- **The unit is the article**, identified the same way as everywhere else (part number, else description). An order counts for an article only when its offer has
  a unit price for that item; the spend is quantity times that price in EUR at the rates in Settings, without VAT. An order whose offer has no price per article
  cannot be split and is counted apart ("not itemised"), never spread by a guess. Cancelled orders and orders before the window are not counted, and the page says how many.
- **ABC by cumulative spend.** Articles sorted by spend; an article is A when the cumulative share before it is under the A boundary, B under the B boundary, C
  after. So the article that crosses a boundary stays in the higher class.
- **XYZ by steadiness.** The quantity ordered per calendar month over the window, months without an order counted as zero; the coefficient of variation
  (population standard deviation over the mean) against two boundaries. The months counted start at the first order in the window, not at the start of the
  window, so a young history is not padded with zeros. With fewer months than the minimum (3 by default) no article gets an XYZ class and the page says why.
- **Boundaries and window are Settings.** 80/95 for ABC and 0.5/1.0 for XYZ are the usual textbook starting values, shown as such; they are the company's to
  change, with the history window (12 months) and the minimum months for XYZ. They are checked (B above A, Y above X).
- **Table and export.** A matrix of the nine classes (articles and spend), the table of articles with share, cumulative share, variation and class, a click on a
  matrix cell filters the table, and an Excel file with the table, the matrix and the basis used (boundaries, orders left out).
- **Nothing here scores, ranks suppliers or changes an order.** The classes describe what was bought.

## Not decided here

- Classes by supplier, customer or category, and by margin instead of spend.
- Using the classes to set stock, reorder points or second-person rules.
- Weekly instead of monthly demand, or a seasonal view.
