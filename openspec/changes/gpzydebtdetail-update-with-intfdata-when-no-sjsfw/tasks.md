## 1. Code Investigation and Constants

- [x] 1.1 Re-check `CClearGpzy::MergeByDayContract()` to identify the exact insertion point after local `node_gpzydebtdetail` matching and existing `pledgeqty == 0` skip logic.
- [x] 1.2 Add meaningful business constants for the SJSFW stock pledge data type `11`, SJSFW stock pledge prefix `GZ`, and fallback remark text `sjsfw无该证券记录，使用日间合约刷新`.

## 2. Fallback Detection

- [x] 2.1 In `MergeByDayContract()`, collect current-scope SJSFW stock pledge keys using `fwsjlb = 11`, `fwzysm` prefix `GZ`, `trim(fwzysm.substr(22, 24))`, and `fwzqdm`.
- [x] 2.2 Use the matched local `node_gpzydebtdetail.pledgesno + stkcode` as the lookup key for determining whether SJSFW has the corresponding Shenzhen A stock pledge record.
- [x] 2.3 Ensure the fallback detection applies only to Shenzhen A local debt details and does not change Shanghai or other market processing.

## 3. Fallback Refresh Implementation

- [x] 3.1 Preserve the existing local-detail matching rules and the existing behavior when no local detail is found.
- [x] 3.2 Preserve the existing skip behavior when the matched local detail's current `pledgeqty` is zero.
- [x] 3.3 When no matching SJSFW key exists, overwrite only `bonusqty`, `backqty`, `wysbqty`, `wyczqty`, and `wyczmatchqty` from `intf_gpzydebtdetail`.
- [x] 3.4 Recompute `pledgeqty` as local `matchqty + bonusqty - backqty - wysbqty`, and clamp negative results to zero.
- [x] 3.5 Do not overwrite `matchqty` or day-real fields such as `backqty_real`, `backbonusamt_real`, `czmatchamt_real`, `backczamt_real`, and `backbonusamtqty_real`.
- [x] 3.6 Update `remark` to `sjsfw无该证券记录，使用日间合约刷新` when the fallback refresh is applied.
- [x] 3.7 Add an info log for successful fallback refresh containing `gpzysno`, `itemno`, `pledgesno`, `stkcode`, and refreshed quantities.

## 4. Verification

- [x] 4.1 Verify that SJSFW-present Shenzhen A records continue to follow the existing processing path and do not receive the new fallback field refresh or fallback remark.
- [x] 4.2 Verify that SJSFW-missing Shenzhen A records refresh the six required fields from `intf_gpzydebtdetail`, recompute `pledgeqty`, update `remark`, and emit the info log.
- [x] 4.3 Verify that fallback recomputation writes `pledgeqty = 0` when the formula result is negative.
- [x] 4.4 Verify that non-Shenzhen-A records are unaffected.
- [x] 4.5 Run OpenSpec validation for `gpzydebtdetail-update-with-intfdata-when-no-sjsfw`.
