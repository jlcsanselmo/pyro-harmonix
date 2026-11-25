### Factor error and monthly correlations

| Pair mode | H3 | Factor policy | Mean bias (%) | Median bias (%) | Monthly MAPE (%) | Held-out r / rho | Pooled r / rho | Folds |
| --- | ---: | --- | ---: | ---: | ---: | --- | --- | ---: |
| union | 7 | unshrunk | 10.83 | 15.61 | 83.55 | 0.872 / 0.726 | 0.988 / 0.757 | 6 |
| union | 7 | monthly_shrunk | 9.40 | 12.51 | 76.06 | 0.884 / 0.721 | 0.990 / 0.761 | 6 |
| union | 6 | unshrunk | 10.83 | 15.61 | 83.55 | 0.872 / 0.726 | 0.988 / 0.757 | 6 |
| union | 6 | monthly_shrunk | 9.31 | 12.09 | 75.78 | 0.884 / 0.721 | 0.990 / 0.758 | 6 |
| codetect | 7 | unshrunk | 100.81 | 104.25 | 190.26 | 0.837 / 0.701 | 0.987 / 0.716 | 6 |
| codetect | 7 | monthly_shrunk | 79.72 | 84.26 | 139.13 | 0.864 / 0.674 | 0.991 / 0.736 | 6 |
| codetect | 6 | unshrunk | 93.79 | 95.53 | 182.98 | 0.834 / 0.699 | 0.987 / 0.715 | 6 |
| codetect | 6 | monthly_shrunk | 73.80 | 74.50 | 133.22 | 0.866 / 0.676 | 0.991 / 0.734 | 6 |

### Fusion sensitivity (monthly-shrunk factors)

| Pair mode | H3 | Fusion | Total/MODIS | c | Mean bias (%) | Monthly MAPE (%) | Worst fold | Folds |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: |
| union | 7 | present_average | 1.492 | 0.508 | 67.36 | 101.84 | 2023 (101.96%) | 6 |
| union | 7 | zero_filled_mean | 1.000 | 0.508 | 4.70 | 38.03 | 2021 (15.87%) | 6 |
| union | 7 | maximum | 1.675 | 0.508 | 84.18 | 113.56 | 2023 (114.67%) | 6 |
| union | 6 | present_average | 1.388 | 0.612 | 58.97 | 96.89 | 2023 (99.51%) | 6 |
| union | 6 | zero_filled_mean | 1.000 | 0.612 | 4.65 | 37.89 | 2021 (15.86%) | 6 |
| union | 6 | maximum | 1.596 | 0.612 | 78.61 | 110.36 | 2023 (111.97%) | 6 |
| codetect | 7 | present_average | 1.991 | 0.472 | 127.93 | 181.71 | 2023 (185.55%) | 6 |
| codetect | 7 | zero_filled_mean | 1.303 | 0.472 | 39.86 | 69.57 | 2023 (56.60%) | 6 |
| codetect | 7 | maximum | 2.188 | 0.472 | 145.70 | 193.03 | 2023 (197.07%) | 6 |
| codetect | 6 | present_average | 1.824 | 0.575 | 112.52 | 168.51 | 2023 (176.98%) | 6 |
| codetect | 6 | zero_filled_mean | 1.280 | 0.575 | 36.90 | 66.61 | 2023 (53.96%) | 6 |
| codetect | 6 | maximum | 2.043 | 0.575 | 132.53 | 181.68 | 2023 (188.65%) | 6 |
