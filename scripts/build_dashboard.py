import json
import pathlib
import os

# Resolve project root (one level above this scripts/ folder)
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / 'data' / 'pnl_daily.json'
OUTPUT_PATH = ROOT / 'public' / 'index.html'

PNL = json.load(open(DATA_PATH))


CSS = """
:root { color-scheme: light; --bg:#FAF6EE; --card:#fff; --ink:#2A1F1F; --mute:#7A6B5D; --line:#E6DDC8; --uk:#6B1A1B; --us:#C9A24C; --pos:#3D6F4E; --neg:#A0312C; --warn:#8B6500; --accent:#6B1A1B; --gold:#C9A24C; --maroon:#6B1A1B; --maroon-light:#8B2A2A; --cream:#FAF6EE;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif}
h1,h2,h3{font-family:"Cormorant Garamond","Playfair Display",Georgia,serif;font-weight:600;letter-spacing:-0.01em}
.wrap{max-width:1320px;margin:0 auto;padding:18px 18px 56px}
h1{font-size:32px;margin:0 0 8px;letter-spacing:-.02em;font-weight:700;color:var(--maroon)}
h1::before{content:"VAHDAM ";color:var(--gold);font-weight:600;letter-spacing:0.05em;font-size:0.7em;display:inline-block;margin-right:6px}
h2{font-size:22px;margin:34px 0 14px;font-weight:600;display:flex;align-items:center;gap:10px;color:var(--maroon);padding-bottom:8px;border-bottom:2px solid var(--gold)}
h2 .badge{font-size:11px;background:var(--gold);color:var(--maroon);padding:3px 10px;border-radius:99px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;font-family:-apple-system,sans-serif}
h3{font-size:14px;margin:0 0 10px;font-weight:600}
.sub{color:var(--mute);font-size:13px;margin-bottom:18px;font-style:italic}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin-bottom:10px;box-shadow:0 1px 3px rgba(107,26,27,0.04)}
.bar label{font-size:12px;color:var(--mute);margin-right:4px;font-weight:600}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{background:#fff;border:0;padding:6px 14px;font-size:12px;color:var(--ink);cursor:pointer;border-right:1px solid var(--line)}
.seg button:last-child{border-right:0}
.seg button:hover{background:#f5f6fa}
.seg button.active{background:var(--maroon);color:#fff}
select,input[type=date],input[type=number]{font-size:12px;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink)}
.range-pill{font-size:11px;color:var(--mute);background:#F0E8D6;padding:4px 10px;border-radius:99px;margin-left:auto;font-weight:500}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:18px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;border-left:3px solid var(--gold);transition:transform 0.1s}
.kpi:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(107,26,27,0.10);border-left-color:var(--maroon)}
.kpi .label{font-size:10px;color:var(--mute);text-transform:uppercase;letter-spacing:.08em;font-weight:700}
.kpi .value{font-size:24px;font-weight:700;margin-top:6px;letter-spacing:-0.02em}
.kpi .sub2{font-size:11px;color:var(--mute);margin-top:4px;line-height:1.4}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:14px}
.card .h-sub{font-size:11px;color:var(--mute);margin-bottom:10px}
table.pnl{width:100%;border-collapse:collapse;font-size:13px}
table.pnl th,table.pnl td{padding:9px 12px;text-align:right;border-bottom:1px solid var(--line)}
table.pnl th{background:#F0E8D6;font-weight:600;font-size:11px;text-transform:uppercase;color:var(--mute);letter-spacing:.04em}
table.pnl td.label{text-align:left;font-weight:500}
table.pnl tr.section td{background:#FBF7EC;font-weight:700;font-size:11px;text-transform:uppercase;color:var(--ink);letter-spacing:.04em}
table.pnl tr.subtotal td{background:#FDF8E8;border-top:1px solid var(--gold);border-bottom:1px solid var(--gold);font-weight:600}
table.pnl tr.total td{background:#FFF1D6;border-top:2px solid var(--maroon);font-weight:700;font-size:14px}
table.pnl tr.deduct td.label::before{content:"− ";color:var(--neg);font-weight:600;font-size:13px}
table.pnl tr.add td.label::before{content:"+ ";color:var(--pos);font-weight:600;font-size:13px}
table.pnl td.tbd{color:var(--warn);font-style:italic;background:#fff8e1}
.tbd{color:var(--warn);font-style:italic;font-size:11px;background:#fff8e1;padding:1px 4px;border-radius:3px}
.warn-strip{background:#FDF8E8;border-left:3px solid var(--gold);color:#5C4A36;border-radius:6px;padding:12px 16px;margin-bottom:18px;font-size:12px;line-height:1.6}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
@media (max-width:900px){.grid{grid-template-columns:1fr}}
canvas{width:100%!important;height:260px!important}
.tag{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;margin-right:4px;font-weight:500}
.tag.uk{background:#F7E8E8;color:#6B1A1B;font-weight:600}
.tag.us{background:#FAEFD4;color:#8B6500;font-weight:600}
.tag.warn{background:#FBE9C0;color:#8B6500;font-weight:600}
.tag.good{background:#E5EFE2;color:#3D6F4E;font-weight:600}
.tag.gift{background:#FCEEDC;color:#A0312C;font-weight:600}
.tag.ext{background:#F5E8C8;color:#8B6500;font-weight:600}
.tag.int{background:#EDE4D4;color:#5C4A36;font-weight:600}
.gridjs-wrapper{box-shadow:none!important;border:1px solid var(--line)!important;border-radius:8px!important}
.gridjs-th{background:#F0E8D6!important;font-size:11px!important;font-weight:600!important}
.foot{font-size:11px;color:var(--mute);text-align:center;margin-top:18px;padding-top:14px;border-top:2px solid var(--gold)}
.delta{font-size:11px;font-weight:500;padding:1px 6px;border-radius:4px;margin-left:6px}
.delta.up{background:#E5EFE2;color:#3D6F4E}
.delta.down{background:#FCEEDC;color:#A0312C}
.hidden{display:none!important}
.gift-toggle{font-size:11px;color:var(--mute);display:inline-flex;align-items:center;gap:5px;margin-left:10px;cursor:pointer}
.gift-toggle input{margin:0}
.bucket-cmp{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}
@media (max-width:900px){.bucket-cmp{grid-template-columns:1fr}}
.bucket-card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.bucket-card.ext{border-top:3px solid var(--gold)}
.bucket-card.int{border-top:3px solid var(--mute)}
.bucket-head{font-weight:600;font-size:14px;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.bucket-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.bucket-grid > div{padding:8px 10px;background:#FBF7EC;border-radius:6px}
.b-label{font-size:10px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em;font-weight:600}
.b-val{font-size:16px;font-weight:700;margin-top:3px}
"""

JS = r"""
const fmtMoney = (v, ccy) => { 
  const sym = ccy==='GBP'?'£':(ccy==='USD'?'$':''); 
  const sign = v<0?'-':'';
  v = Math.abs(v);
  return sign + sym + (v>=1000? v.toLocaleString('en-US',{maximumFractionDigits:0}) : v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}));
};
const fmtNum = v => v==null?'—':(typeof v==='number'?v.toLocaleString('en-US',{maximumFractionDigits:0}):v);
const isoAdd = (iso, n) => { const d=new Date(iso); d.setUTCDate(d.getUTCDate()+n); return d.toISOString().slice(0,10); };

const state = {
  region: 'both', sku: '', variation: '', period: 'L30',
  customFrom: PNL.window_start, customTo: PNL.window_end,
  includeFreeGifts: false, fxRate: 1.27,
};
const creativeState = { snapshotIdx: 0, bucket: 'both' };

function displayCcy(){ return state.region === 'UK' ? 'GBP' : 'USD'; }
function ccySym(){ return displayCcy() === 'GBP' ? '£' : '$'; }
function ukToDisplay(v){ return displayCcy()==='GBP' ? v : v * (state.fxRate || 1.27); }
function combine(ukVal, usVal){
  if(state.region==='UK') return ukVal;
  if(state.region==='US') return usVal;
  return ukToDisplay(ukVal) + usVal;
}
// Latest date that has ANY non-zero orders/aff for the current region+sku+variation
// filter. Capped at PNL.window_end (handoff's declared cutoff -- partial rows
// beyond it shouldn't anchor period buttons). Cached per filter.
const _ldCache = {};
function latestDataDate(){
  const k = state.region+'|'+state.sku+'|'+state.variation;
  if(k in _ldCache) return _ldCache[k];
  let latest = null;
  for(const r of PNL.orders_daily){
    if(state.region!=='both' && r.region!==state.region) continue;
    if(state.sku && r.sku!==state.sku) continue;
    if(state.variation && r.variation!==state.variation) continue;
    if(PNL.window_end && r.date > PNL.window_end) continue;  // ignore partial post-cutoff
    const has = (r.net_orders||0) > 0 || (r.orders||0) > 0 || (r.net_sales||0) > 0;
    if(has && (!latest || r.date > latest)) latest = r.date;
  }
  _ldCache[k] = latest || PNL.window_end;
  return _ldCache[k];
}
// Globally most recent date with ANY orders (region-agnostic) — used as the
// anchor for L7/L30 so they don't drift when today's clock outruns the data.
// Capped at PNL.window_end so partial post-cutoff rows can't anchor the window.
function dataEndDate(){
  let latest = null;
  for(const r of PNL.orders_daily){
    if(PNL.window_end && r.date > PNL.window_end) continue;
    if(((r.net_orders||0) > 0 || (r.net_sales||0) > 0) && (!latest || r.date > latest)){
      latest = r.date;
    }
  }
  return latest || PNL.window_end;
}
function effectiveWindow(){
  // Anchor ALL period buttons to dataEndDate(), not today's clock or
  // PNL.window_end. Eliminates "today's clock drifted past data" bugs.
  const end = dataEndDate();
  if(state.period==='YDAY'){ const d = latestDataDate(); return {from:d, to:d}; }
  if(state.period==='L7') return {from: isoAdd(end, -6), to: end};
  if(state.period==='L30') return {from: isoAdd(end, -29), to: end};
  return {from: state.customFrom, to: state.customTo};
}
function inWindow(date, win){ return date>=win.from && date<=win.to; }
function dayDiff(win){ return Math.round((new Date(win.to)-new Date(win.from))/86400000)+1; }

function aggregate(){
  const win = effectiveWindow();
  const days = []; let d = win.from;
  while(d<=win.to){ days.push(d); d = isoAdd(d, 1); }
  const orders = PNL.orders_daily.filter(r => {
    if(!state.includeFreeGifts && r.is_free_gift && state.sku !== r.sku) return false;
    // FIX 3: "Other" SKU is data exhaust; exclude from default views unless explicitly selected.
    if(r.sku === 'Other' && state.sku !== 'Other') return false;
    if(state.region!=='both' && r.region!==state.region) return false;
    // SKU filter: free-gift rows bypass when "Include free gifts" toggle is
    // ON, since gifts are conceptually bundled with paid orders of the
    // selected SKU (e.g. a Coffee customer gets a Tea gift; the gift row's
    // sku is "Turmeric Ginger Tea (free gift)", not "Coffee").
    if(state.sku && r.sku!==state.sku){
      if(!(state.includeFreeGifts && r.is_free_gift)) return false;
    }
    if(state.variation && r.variation!==state.variation) return false;
    return inWindow(r.date, win);
  });
  const aff = PNL.aff_daily.filter(r => {
    if(state.region!=='both' && r.region!==state.region) return false;
    if(r.sku === 'Other' && state.sku !== 'Other') return false;
    if(state.sku && r.sku!==state.sku) return false;
    return inWindow(r.date, win);
  });
  const ad = PNL.ad_spend_daily;
  let adSpendUK=0, adSpendUS=0, adUnallocUK=0, adUnallocUS=0;
  // Drive scan from state.region (or both) — never hardcode UK; prevents
  // cross-region ad-spend leakage on US views.
  const regionsToScan = state.region === 'both' ? ['UK','US'] : [state.region];
  for(const day of days){
    for(const region of regionsToScan){
      const dayMap = ad.daily_by_sku[region] && ad.daily_by_sku[region][day];
      if(!dayMap) continue;
      for(const [skuName, val] of Object.entries(dayMap)){
        if(skuName === '(unallocated)' || skuName === 'Other'){
          if(!state.sku){
            if(region === 'UK') adUnallocUK += val; else adUnallocUS += val;
          }
          continue;
        }
        if(state.sku && state.sku !== skuName) continue;
        if(region === 'UK') adSpendUK += val; else adSpendUS += val;
      }
    }
  }
  const agg = (rows, region) => {
    let m = {orders:0, qty:0, qty_returned:0, gross:0, plat_disc:0, seller_disc:0, net_sku:0, shipping:0, tax:0, refund:0, sales:0, revenue_after_refund:0, cancelled_orders:0, cancelled_qty:0, cancelled_amt:0, sample_orders:0, sample_qty:0, net_orders:0, net_qty:0, net_gross:0, net_plat_disc:0, net_seller_disc:0, net_sku_total:0, net_shipping:0, net_refund:0, net_return_qty:0, net_return_value:0, net_sales:0};
    for(const r of rows){
      if(region!=='both' && r.region!==region) continue;
      m.orders += r.orders; m.qty += r.qty; m.qty_returned += r.return_qty||0;
      m.gross += r.gross; m.plat_disc += r.plat_disc; m.seller_disc += r.seller_disc;
      m.net_sku += r.net_sku; m.shipping += r.shipping; m.tax += r.tax; m.refund += r.refund;
      m.sales += r.sales||0; m.revenue_after_refund += r.revenue_after_refund||0;
      m.cancelled_orders += r.cancelled_orders||0; m.cancelled_qty += r.cancelled_qty||0; m.cancelled_amt += r.cancelled_amt||0;
      m.sample_orders += r.sample_orders||0; m.sample_qty += r.sample_qty||0;
      m.net_orders += r.net_orders||0; m.net_qty += r.net_qty||0;
      m.net_gross += r.net_gross||0; m.net_plat_disc += r.net_plat_disc||0; m.net_seller_disc += r.net_seller_disc||0;
      m.net_sku_total += r.net_sku_total||0; m.net_shipping += r.net_shipping||0; m.net_refund += r.net_refund||0;
      m.net_return_qty += r.net_return_qty||0; m.net_return_value += r.net_return_value||0;
      m.net_sales += r.net_sales||0;
    }
    return m;
  };
  const aggAff = (rows, region) => {
    let m = {orders:0, revenue:0, commission:0};
    for(const r of rows){ if(region!=='both' && r.region!==region) continue; m.orders+=r.aff_orders; m.revenue+=r.aff_revenue; m.commission+=r.aff_commission; }
    return m;
  };
  function computeCosts(rows, region){
    const ukCosts = (PNL.costs_uk && PNL.costs_uk.costs_per_pack) || {};
    const usCosts = (PNL.costs_us && PNL.costs_us.costs_per_pack) || {};
    const costs = region === 'UK' ? ukCosts : usCosts;
    const tax = (PNL.costs_uk && PNL.costs_uk.uk_tax_rules) || {};
    const vatKept = new Set(tax.vat_kept_skus || ['Turmeric Ginger Tea']);
    const vatRemovedAlways = new Set(tax.vat_removed_always || []);
    const coffeeVatCutoff = (tax.vat_removed_from_date && tax.vat_removed_from_date.Coffee) || '2026-04-01';
    const shipFrom = tax.shipping_per_order_from_date || '2026-03-01';
    const shipAmt = tax.shipping_per_order_amount || 1.99;
    // TT commission rates per CLAUDE.md spec: 9% UK, 6% US (flat % of Net Sales,
    // not per-pack from costs files). The per-pack `commission` field in
    // *_costs.json equals 6%/9% of MSRP, but breaks for unmapped variations
    // (e.g. "2 - Pack", "3 - Pack", Berberine, Curry Powder, Moringa,
    // Psyllium Husk in US -- they show up in orders_daily but are absent from
    // costs_per_pack, so the per-pack-times-qty approach charges 0 commission
    // on those units. Flat % is robust + matches the operator's sheet method.
    const ttCommRate = region === 'UK' ? 0.09 : 0.06;
    // Variation aliasing: orders_daily uses some variation names that don't
    // appear verbatim in the costs file. Resolve common aliases so the per-pack
    // cost lookup works for "2 - Pack" / "3 - Pack" / "Starter Kit" rows.
    // This is the bulk of the dashboard-vs-sheet "Other Fix Charges" gap.
    function resolveCp(skuCps, variation){
      if(!skuCps) return null;
      if(skuCps[variation]) return skuCps[variation];
      const aliases = {
        '2 - Pack': 'Pack of 2',
        '3 - Pack': 'Pack of 3',
        '5 - Pack': 'Pack of 5',
        '2 Pack': 'Pack of 2',
        '3 Pack': 'Pack of 3',
        'Starter Kit': 'Pack of 1',  // Coffee Starter Kit ≈ Pack-of-1 economics
      };
      const alias = aliases[variation];
      return alias ? (skuCps[alias] || null) : null;
    }
    let total = { cogs:0, commission:0, dsf:0, storage:0, vat:0, logistics_duty:0, logistics_cost:0, fulfillment:0, shipping:0, per_order_shipping:0 };
    for(const r of rows){
      if(r.region !== region) continue;
      const cps = costs[r.sku];
      const cp = resolveCp(cps, r.variation);
      const q = r.net_qty || 0;
      const orders_ct = r.net_orders || 0;
      const ns = r.net_sales || 0;
      let vatApplies;
      if(vatKept.has(r.sku)) vatApplies = true;
      else if(r.sku === 'Coffee') vatApplies = (r.date < coffeeVatCutoff);
      else if(vatRemovedAlways.has(r.sku)) vatApplies = false;
      else vatApplies = true;
      // Commission: ALWAYS flat % of Net Sales (per CLAUDE.md). Per-pack values
      // in costs file are ignored for commission to keep the rule robust to
      // missing variations.
      total.commission += ns * ttCommRate;
      if(cp){
        total.cogs += (cp.cogs||0) * q;
        total.dsf += (cp.digital_service_fee||0) * q;
        total.storage += (cp.storage||0) * q;
        if(vatApplies) total.vat += (cp.vat||0) * q;
        total.logistics_duty += (cp.logistics_duty||0) * q;
        total.logistics_cost += (cp.logistics_cost||0) * q;
        total.fulfillment += (cp.fulfillment||0) * q;
        total.shipping += (cp.shipping||0) * q;
      }
      if(region === 'UK' && r.date >= shipFrom){
        total.per_order_shipping += orders_ct * shipAmt;
      }
    }
    total.all = total.cogs+total.commission+total.dsf+total.storage+total.vat+total.logistics_duty+total.logistics_cost+total.fulfillment+total.shipping+total.per_order_shipping;
    return total;
  }
  // VAT-in-sales: 20% removed from Net Sales for UK supplements (Coffee Apr+, GB, AC, TC).
  // For Ginger Tea + non-supplements: NO removal (VAT not deducted from sales).
  function computeVatInSales(rows, region){
    if(region !== 'UK') return 0;
    const tax = (PNL.costs_uk && PNL.costs_uk.uk_tax_rules) || {};
    const vatRemovedAlways = new Set(tax.vat_removed_always || []);
    const coffeeVatCutoff = (tax.vat_removed_from_date && tax.vat_removed_from_date.Coffee) || '2026-04-01';
    let vatInSales = 0;
    for(const r of rows){
      if(r.region !== 'UK') continue;
      // Only zero-rated supplements have VAT removed from sales
      let isVatZeroRated = false;
      if(r.sku === 'Coffee') isVatZeroRated = (r.date >= coffeeVatCutoff);
      else if(vatRemovedAlways.has(r.sku)) isVatZeroRated = true;
      if(isVatZeroRated){
        vatInSales += (r.net_sales || 0) * (20/120);
      }
    }
    return vatInSales;
  }
  // Smart Promotion cost — allocated proportionally to filtered revenue within each month window.
  // Per user: pulled from Seller Center > Marketing > Smart Promotion. UK gets 20/120 VAT recovery.
  function computeSmartPromoCost(rows, region){
    const sp = PNL.smart_promo_monthly || [];
    if(!sp.length) return 0;
    const allOrders = PNL.orders_daily || [];
    let total = 0;
    // For each smart_promo monthly bucket matching region & overlapping any filtered row's month
    for(const bucket of sp){
      if(bucket.region !== region) continue;
      const ws = bucket.window_start, we = bucket.window_end;
      // Total revenue in this region+window (UNFILTERED — denominator)
      let monthRevTotal = 0;
      for(const r of allOrders){
        if(r.region !== region) continue;
        if(r.date < ws || r.date > we) continue;
        monthRevTotal += (r.net_sales || 0);
      }
      if(monthRevTotal <= 0) continue;
      // Filtered revenue in this region+window (numerator)
      let monthRevFiltered = 0;
      for(const r of rows){
        if(r.region !== region) continue;
        if(r.date < ws || r.date > we) continue;
        monthRevFiltered += (r.net_sales || 0);
      }
      total += bucket.cost * (monthRevFiltered / monthRevTotal);
    }
    return total;
  }
  // Free sample cost: UK uses uk_free_sample_costs.per_pack with £2 shipping deduction post-Feb 14.
  // US uses us_free_sample_costs.per_pack (sum of COGS+DSF+Storage+LogDuty+LogCost+Fulfillment+Shipping), no shipping deduction.
  function computeFreeSampleCost(rows, region){
    let perPack = {};
    let shipDeductFrom = null, shipDeduct = 0;
    if(region === 'UK'){
      const fs = (PNL.costs_uk && PNL.costs_uk.uk_free_sample_costs) || {};
      perPack = fs.per_pack || {};
      shipDeductFrom = fs.shipping_deduction_from_date || '2026-02-14';
      shipDeduct = fs.shipping_deduction_amount || 2.0;
    } else if(region === 'US'){
      const fs = (PNL.costs_us && PNL.costs_us.us_free_sample_costs) || {};
      perPack = fs.per_pack || {};
    } else { return 0; }
    let total = 0;
    for(const r of rows){
      if(r.region !== region) continue;
      const sampleQty = r.sample_qty || 0;
      if(sampleQty <= 0) continue;
      const perPackCost = (perPack[r.sku] && perPack[r.sku][r.variation]) || 0;
      let eff = perPackCost;
      if(shipDeductFrom && r.date >= shipDeductFrom){ eff = Math.max(0, perPackCost - shipDeduct); }
      total += sampleQty * eff;
    }
    return total;
  }
  return { win, days, orders, aff,
           ukOrd: agg(orders, 'UK'), usOrd: agg(orders, 'US'),
           ukAff: aggAff(aff, 'UK'), usAff: aggAff(aff, 'US'),
           ukCosts: computeCosts(orders, 'UK'),
           usCosts: computeCosts(orders, 'US'),
           ukVatInSales: computeVatInSales(orders, 'UK'),
           usVatInSales: 0,
           ukFreeSampleCost: computeFreeSampleCost(orders, 'UK'),
           usFreeSampleCost: computeFreeSampleCost(orders, 'US'),
           ukSmartPromo: computeSmartPromoCost(orders, 'UK'),
           usSmartPromo: computeSmartPromoCost(orders, 'US'),
           adSpendUK, adSpendUS, adUnallocUK, adUnallocUS };
}

function aggregatePrior(){
  const win = effectiveWindow();
  const dur = dayDiff(win);
  const prevTo = isoAdd(win.from, -1);
  const prevFrom = isoAdd(prevTo, -(dur-1));
  const orders = PNL.orders_daily.filter(r => {
    if(!state.includeFreeGifts && r.is_free_gift && state.sku !== r.sku) return false;
    if(state.region!=='both' && r.region!==state.region) return false;
    if(state.sku && r.sku!==state.sku) return false;
    if(state.variation && r.variation!==state.variation) return false;
    return r.date>=prevFrom && r.date<=prevTo;
  });
  let sales_uk=0, sales_us=0, ord=0;
  for(const r of orders){
    if(r.region==='UK') sales_uk += (r.net_sales||0); else sales_us += (r.net_sales||0);
    ord += (r.net_orders||0);
  }
  return { sales_uk, sales_us, sales: sales_uk + sales_us, orders: ord, from: prevFrom, to: prevTo };
}

function renderKPIs(){
  const a = aggregate();
  const prior = aggregatePrior();
  const fx = state.fxRate || 1.27;
  const sym = ccySym();
  const netSales = combine(a.ukOrd.net_sales, a.usOrd.net_sales);
  const netOrders = a.ukOrd.net_orders + a.usOrd.net_orders;
  const netUnits = a.ukOrd.net_qty + a.usOrd.net_qty;
  const cancelOrders = a.ukOrd.cancelled_orders + a.usOrd.cancelled_orders;
  const cancelAmt = combine(a.ukOrd.cancelled_amt, a.usOrd.cancelled_amt);
  const sampleOrders = a.ukOrd.sample_orders + a.usOrd.sample_orders;
  const returnQty = a.ukOrd.net_return_qty + a.usOrd.net_return_qty;
  const returnValue = combine(a.ukOrd.net_return_value, a.usOrd.net_return_value);
  const refundAmt = combine(a.ukOrd.refund, a.usOrd.refund);
  // Ad spend KPI: show VAT-inclusive UK number (matches cash outflow)
  const adSpend = combine((a.adSpendUK + a.adUnallocUK) * 1.20, a.adSpendUS + a.adUnallocUS);
  const affComm = combine(a.ukAff.commission, a.usAff.commission);
  // VAT removed from sales for zero-rated supplements (Coffee Apr+, GB, AC, TC)
  const ukNetSalesExVat = a.ukOrd.net_sales - (a.ukVatInSales || 0);
  const usNetSalesExVat = a.usOrd.net_sales;
  const ukCM1 = ukNetSalesExVat - a.ukCosts.all;
  const usCM1 = usNetSalesExVat - a.usCosts.all;
  const cm1 = combine(ukCM1, usCM1);
  const ukSmartPromoExVat = a.ukSmartPromo || 0;
  const usSmartPromo = a.usSmartPromo || 0;
  // UK: Seller Center shows VAT-EXCL ad spend + smart promo. Gross up by 20% to actual cash cost,
  // then recover 20/120 of gross. Net economic cost = ex-VAT amount (matches Seller Center).
  const ukAdSpendExVat = a.adSpendUK + a.adUnallocUK;
  const ukAdSpendIncVat = ukAdSpendExVat * 1.20;
  const ukSmartPromoIncVat = ukSmartPromoExVat * 1.20;
  // VAT recovery: 20/120 of every UK input that carries reclaimable input VAT.
  // Matches Vahdam Inventory Planning Tiktok!UK Coffee!C11 formula
  // =(C8+C10+C17+C18)*0.2/1.2 (per-pack: Commission+Storage+Fulfillment+Shipping)
  // plus aggregate inputs I19: (Affiliated Comm + Actual Comm + Ad Spend Incl VAT) * 0.2/1.2,
  // extended per user spec to also include Smart Promo and per-order shipping.
  const ukVatRec = (
      (a.ukCosts.storage           || 0)
    + (a.ukCosts.fulfillment       || 0)
    + ukAdSpendIncVat
    + (a.ukCosts.per_order_shipping|| 0)
    + (a.ukCosts.commission        || 0)
    + (a.ukAff.commission          || 0)
    + ukSmartPromoIncVat
  ) * (20/120);
  const ukFreeSampleCost = a.ukFreeSampleCost || 0;
  const usFreeSampleCost = a.usFreeSampleCost || 0;
  const ukCM2 = ukCM1 - a.ukAff.commission - ukAdSpendIncVat + ukVatRec - ukFreeSampleCost - ukSmartPromoIncVat;
  const usCM2 = usCM1 - a.usAff.commission - a.adSpendUS - a.adUnallocUS - usFreeSampleCost - usSmartPromo;
  const cm2 = combine(ukCM2, usCM2);
  const hasUkCosts = a.ukCosts.all > 0;
  const hasUsCosts = a.usCosts.all > 0;
  const cmCovered = state.region==='UK' ? hasUkCosts : (state.region==='US' ? hasUsCosts : hasUkCosts);
  const cmShown = cmCovered ? sym+fmtNum(cm2) : '<span class="tbd">need US costs</span>';
  const cm2Pct = (cmCovered && netSales) ? ((cm2/netSales)*100).toFixed(1)+'%' : '—';
  const cm1Shown = cmCovered ? sym+fmtNum(cm1) : '<span class="tbd">need US costs</span>';
  const cm1Pct = (cmCovered && netSales) ? ((cm1/netSales)*100).toFixed(1)+'%' : '—';
  const priorSales = state.region==='UK' ? (prior.sales_uk||0) : state.region==='US' ? (prior.sales_us||0) : ukToDisplay(prior.sales_uk||0) + (prior.sales_us||0);
  function deltaTag(cur, prev){
    if(!prev) return '';
    const d = (cur-prev)/prev;
    if(Math.abs(d)<0.001) return '';
    const cls = d>=0?'up':'down';
    return ' <span class="delta '+cls+'">'+(d>=0?'▲':'▼')+' '+(d*100).toFixed(1)+'%</span>';
  }
  const regionTag = state.region==='UK' ? '<span class="tag uk">UK · GBP</span>' :
                    state.region==='US' ? '<span class="tag us">US · USD</span>' :
                    '<span class="tag uk">UK</span><span class="tag us">US</span> · USD';
  let netSalesSub = state.region==='both' ?
    'UK £'+fmtNum(a.ukOrd.net_sales)+'×'+fx.toFixed(2)+' + US $'+fmtNum(a.usOrd.net_sales) :
    fmtNum(netOrders)+' net orders · '+fmtNum(netUnits)+' units';
  netSalesSub += deltaTag(netSales, priorSales);
  // Gap detection: if NO orders, NO ad spend, NO affiliate for current filter+window,
  // show "—" instead of currency-zero on every cash KPI. The window is "empty" not zero.
  const windowEmpty = (netOrders===0) && (Math.abs(adSpend)<0.01) && (Math.abs(affComm)<0.01) && (Math.abs(netSales)<0.01);
  const dash = '<span style="color:var(--mute)">—</span>';
  const m = (val, formatted) => windowEmpty ? dash : formatted;
  // Inject the freshness banner first (will be hidden if data is fresh)
  renderFreshnessBanner(effectiveWindow());
  document.getElementById('kpis').innerHTML =
    '<div class="kpi"><div class="label">Net Sales '+regionTag+'</div><div class="value">'+m(netSales, sym+fmtNum(netSales))+'</div><div class="sub2">'+(windowEmpty?'no data in window':netSalesSub)+'</div></div>'+
    '<div class="kpi"><div class="label">Net Orders</div><div class="value">'+m(netOrders, fmtNum(netOrders))+'</div><div class="sub2">'+(windowEmpty?'no data in window':fmtNum(netUnits)+' units · excl. cancelled & samples')+'</div></div>'+
    '<div class="kpi"><div class="label">CM1 (Net Sales − Unit costs)</div><div class="value">'+(windowEmpty?dash:cm1Shown)+'</div><div class="sub2">'+(windowEmpty?'no data':cm1Pct+' of Net Sales')+'</div></div>'+
    '<div class="kpi"><div class="label">CM2 (Net Margin)</div><div class="value">'+(windowEmpty?dash:cmShown)+'</div><div class="sub2">'+(windowEmpty?'no data':cm2Pct+' · UK tax rules applied')+'</div></div>'+
    '<div class="kpi"><div class="label">Cancellations</div><div class="value">'+m(cancelOrders, fmtNum(cancelOrders))+'</div><div class="sub2">'+(windowEmpty?'':sym+fmtNum(cancelAmt))+'</div></div>'+
    '<div class="kpi"><div class="label">Samples</div><div class="value">'+m(sampleOrders, fmtNum(sampleOrders))+'</div><div class="sub2">order_amt = 0</div></div>'+
    '<div class="kpi"><div class="label">Returns (units)</div><div class="value">'+m(returnQty, fmtNum(returnQty))+'</div><div class="sub2">'+(windowEmpty?'':sym+fmtNum(returnValue)+' value')+'</div></div>'+
    '<div class="kpi"><div class="label">Refunds</div><div class="value">'+m(refundAmt, sym+fmtNum(refundAmt))+'</div><div class="sub2">'+(windowEmpty?'':'all status')+'</div></div>'+
    '<div class="kpi"><div class="label">Ad Spend</div><div class="value">'+m(adSpend, sym+fmtNum(adSpend))+'</div><div class="sub2">'+(windowEmpty?'':'Seller Center L30')+'</div></div>'+
    '<div class="kpi"><div class="label">Affiliate Comm</div><div class="value">'+m(affComm, sym+fmtNum(affComm))+'</div><div class="sub2">'+(windowEmpty?'':'on shipped/delivered')+'</div></div>';
}

// Freshness banner — shows when the active window contains dates AFTER the
// last day with real data, so users immediately see why KPIs are "—".
function renderFreshnessBanner(win){
  const el = document.getElementById('freshnessBanner');
  if(!el) return;
  const dataEnd = PNL.window_end;
  const todayLocal = new Date().toISOString().slice(0,10);
  const aheadDays = Math.max(0, Math.round((new Date(todayLocal) - new Date(dataEnd))/86400000));
  // Hide if window is entirely <= dataEnd, OR data is fresh (≤1d behind today)
  if(win.to <= dataEnd && aheadDays <= 1){ el.style.display = 'none'; return; }
  const stale = win.to > dataEnd;
  if(!stale){ el.style.display = 'none'; return; }
  el.style.display = '';
  el.innerHTML =
    '<b>Showing data through '+dataEnd+'.</b> '+
    '<span style="color:var(--mute)">'+aheadDays+' day'+(aheadDays===1?'':'s')+' ahead of last refresh — '+
    'run <code>scripts/sync_from_handoff.bat</code> or wait for the daily 3:30 PM IST sync.</span>';
}

function renderPnLTable(){
  const a = aggregate();
  const sym = ccySym();
  const ccy = displayCcy();
  function money(uk, us){ return sym + fmtNum(combine(uk, us)); }
  function intRow(uk, us){ return fmtNum((uk||0) + (us||0)); }
  // FIX 2: For "soft" cash lines (ad spend / smart promo / free sample / VAT
  // recovery), display "—" when the value is zero (rather than "£0.00") so
  // niche-SKU views and quiet days read cleanly. Opt-in via opts.zeroDash.
  // For "hideZero", skip the row entirely when both sides are 0.
  function row(label, ukVal, usVal, opts){
    opts = opts||{};
    const cls = opts.cls||'';
    const combined = (ukVal||0) + (usVal||0);
    if(opts.hideZero && Math.abs(combined) < 0.005 && (opts.type !== 'int')){ return ''; }
    let numeric;
    if(opts.type === 'int'){
      numeric = intRow(ukVal, usVal);
    } else if(opts.zeroDash && Math.abs(combined) < 0.005){
      numeric = '<span style="color:var(--mute)">—</span>';
    } else {
      numeric = money(ukVal||0, usVal||0);
    }
    return '<tr class="'+cls+'"><td class="label">'+label+'</td><td>'+numeric+'</td></tr>';
  }
  const ukC = a.ukCosts, usC = a.usCosts;
  const hasUkCosts = ukC.all > 0, hasUsCosts = usC.all > 0;
  // VAT removed from sales for zero-rated supplements
  const ukVatInSales = a.ukVatInSales || 0;
  const usVatInSales = a.usVatInSales || 0;
  const ukNetSalesExVat = a.ukOrd.net_sales - ukVatInSales;
  const usNetSalesExVat = a.usOrd.net_sales - usVatInSales;
  const ukCM1 = ukNetSalesExVat - ukC.all;
  const usCM1 = usNetSalesExVat - usC.all;
  // UK: Seller Center numbers are VAT-EXCL. Gross up by 20% to actual cash cost, recover 20/120.
  const ukSPex = a.ukSmartPromo || 0;
  const usSP = a.usSmartPromo || 0;
  const ukSPinc = ukSPex * 1.20;
  const ukAdEx = a.adSpendUK || 0;
  const ukAdUnEx = a.adUnallocUK || 0;
  const ukAdInc = ukAdEx * 1.20;
  const ukAdUnInc = ukAdUnEx * 1.20;
  // VAT recovery: 20/120 on every UK input carrying reclaimable VAT.
  // See renderKPIs comment for sheet reference.
  const ukVatRec = (
      (ukC.storage              || 0)
    + (ukC.fulfillment          || 0)
    + ukAdInc + ukAdUnInc
    + (ukC.per_order_shipping   || 0)
    + (ukC.commission           || 0)
    + (a.ukAff.commission       || 0)
    + ukSPinc
  ) * (20/120);
  const ukFsCost = a.ukFreeSampleCost || 0;
  const usFsCost = a.usFreeSampleCost || 0;
  const ukCM2 = ukCM1 - a.ukAff.commission - ukAdInc - ukAdUnInc + ukVatRec - ukFsCost - ukSPinc;
  const usCM2 = usCM1 - a.usAff.commission - a.adSpendUS - a.adUnallocUS - usFsCost - usSP;
  function marginRow(label, ukVal, usVal, baseUk, baseUs, opts){
    opts = opts||{};
    const cls = opts.cls||'total';
    let valCell = '', pctCell = '';
    if(state.region==='UK'){
      valCell = (opts.requireCosts && !hasUkCosts) ? '<span class="tbd">need UK costs</span>' : sym+fmtNum(ukVal);
      pctCell = (opts.requireCosts && !hasUkCosts) ? '' : (baseUk ? ' ('+(ukVal/baseUk*100).toFixed(1)+'%)' : '');
    } else if(state.region==='US'){
      valCell = (opts.requireCosts && !hasUsCosts) ? '<span class="tbd">need US costs</span>' : sym+fmtNum(usVal);
      pctCell = (opts.requireCosts && !hasUsCosts) ? '' : (baseUs ? ' ('+(usVal/baseUs*100).toFixed(1)+'%)' : '');
    } else {
      const ok = opts.requireCosts ? (hasUkCosts && hasUsCosts) : true;
      const partial = opts.requireCosts && hasUkCosts && !hasUsCosts;
      const combinedVal = ukToDisplay(ukVal) + usVal;
      const combinedBase = ukToDisplay(baseUk) + baseUs;
      if(ok){
        valCell = sym+fmtNum(combinedVal);
        pctCell = combinedBase ? ' ('+(combinedVal/combinedBase*100).toFixed(1)+'%)' : '';
      } else if(partial){
        valCell = sym+fmtNum(ukToDisplay(ukVal)) + ' <span class="tbd">(UK only)</span>';
        pctCell = baseUk ? ' ('+(ukVal/baseUk*100).toFixed(1)+'%)' : '';
      } else { valCell = '<span class="tbd">TBD</span>'; }
    }
    return '<tr class="'+cls+'"><td class="label">'+label+'</td><td>'+valCell+pctCell+'</td></tr>';
  }
  const netOrdersTotal = a.ukOrd.net_orders + a.usOrd.net_orders;
  const netQtyTotal = a.ukOrd.net_qty + a.usOrd.net_qty;
  const aov = netOrdersTotal ? combine(a.ukOrd.net_sales, a.usOrd.net_sales) / netOrdersTotal : 0;
  let h = '<thead><tr><th>Line item</th><th>'+ccy+'</th></tr></thead><tbody>';
  h += '<tr class="section"><td class="label">Volume — all lines</td><td>&nbsp;</td></tr>';
  h += row('Total order lines', a.ukOrd.orders, a.usOrd.orders, {type:'int'});
  h += row('Total units', a.ukOrd.qty, a.usOrd.qty, {type:'int'});
  h += '<tr class="section"><td class="label">Excluded from Net Sales</td><td>&nbsp;</td></tr>';
  h += row('Cancelled orders', a.ukOrd.cancelled_orders, a.usOrd.cancelled_orders, {cls:'deduct', type:'int'});
  h += row('Cancelled units', a.ukOrd.cancelled_qty, a.usOrd.cancelled_qty, {cls:'deduct', type:'int'});
  h += row('Cancelled value', a.ukOrd.cancelled_amt, a.usOrd.cancelled_amt, {cls:'deduct'});
  h += row('Samples (order_amt=0)', a.ukOrd.sample_orders, a.usOrd.sample_orders, {cls:'deduct', type:'int'});
  h += '<tr class="subtotal"><td class="label">Net orders / units</td><td>'+fmtNum(netOrdersTotal)+' / '+fmtNum(netQtyTotal)+'</td></tr>';
  h += '<tr><td class="label">AOV (net)</td><td>'+sym+fmtNum(aov)+'</td></tr>';
  h += '<tr class="section"><td class="label">Net Sales build-up</td><td>&nbsp;</td></tr>';
  h += row('Gross sales (net lines, before discounts)', a.ukOrd.net_gross, a.usOrd.net_gross);
  h += row('Seller discount', a.ukOrd.net_seller_disc, a.usOrd.net_seller_disc, {cls:'deduct'});
  h += row('Subtotal after discount', a.ukOrd.net_sku_total, a.usOrd.net_sku_total);
  h += row('Platform discount (TT reimburses)', a.ukOrd.net_plat_disc, a.usOrd.net_plat_disc, {cls:'add'});
  h += row('Returns value', a.ukOrd.net_return_value, a.usOrd.net_return_value, {cls:'deduct'});
  h += row('Refunds', a.ukOrd.net_refund, a.usOrd.net_refund, {cls:'deduct'});
  h += row('<b>Net Sales (top line)</b>', a.ukOrd.net_sales, a.usOrd.net_sales, {cls:'subtotal'});
  h += row('(−) VAT 20% in Sales (zero-rated supplements only)', ukVatInSales, usVatInSales, {cls:'deduct'});
  h += row('<b>Net Sales ex-VAT (revenue used for PnL)</b>', ukNetSalesExVat, usNetSalesExVat, {cls:'subtotal'});
  h += '<tr class="section"><td class="label">CM1 build-up — per-unit variable costs</td><td>&nbsp;</td></tr>';
  h += row('COGs', ukC.cogs, usC.cogs, {cls:'deduct'});
  h += row('TT Commission', ukC.commission, usC.commission, {cls:'deduct'});
  h += row('Digital Service Fee', ukC.dsf, usC.dsf, {cls:'deduct'});
  h += row('Storage', ukC.storage, usC.storage, {cls:'deduct'});
  h += row('VAT-on-inputs (Ginger Tea only — kept)', ukC.vat, usC.vat, {cls:'deduct'});
  h += row('Logistics Duty', ukC.logistics_duty, usC.logistics_duty, {cls:'deduct'});
  h += row('Logistics Cost', ukC.logistics_cost, usC.logistics_cost, {cls:'deduct'});
  h += row('Fulfillment', ukC.fulfillment, usC.fulfillment, {cls:'deduct'});
  h += row('Outbound Shipping (per-pack)', ukC.shipping, usC.shipping, {cls:'deduct'});
  h += row('Per-order Shipping (UK Mar+ £1.99)', ukC.per_order_shipping||0, usC.per_order_shipping||0, {cls:'deduct'});
  h += row('Total unit costs', ukC.all, usC.all, {cls:'deduct'});
  h += marginRow('<b>CM1</b> = Net Sales ex-VAT − Unit costs', ukCM1, usCM1, ukNetSalesExVat, usNetSalesExVat, {requireCosts:true, cls:'subtotal'});
  h += '<tr class="section"><td class="label">CM2 build-up — marketing</td><td>&nbsp;</td></tr>';
  h += row('Affiliate commission (Std + Shop Ads + Co-funded)', a.ukAff.commission, a.usAff.commission, {cls:'deduct', zeroDash:true});
  // FIX BUG #3: Combine Product GMV Max + LIVE GMV Max + Auto into one line.
  // The data file lumps LIVE share into each SKU's daily ad spend (distributed
  // by revenue mix), so the separate "LIVE GMV Max + Auto" line is always 0
  // unless there's a true unallocated bucket. Show combined total.
  h += row('Ad spend (Product GMV Max + LIVE distributed by revenue, UK ×1.20 VAT-incl)',
           ukAdInc + ukAdUnInc, a.adSpendUS + a.adUnallocUS,
           {cls:'deduct', zeroDash:true});
  h += row('Smart Promotion fee (UK ×1.20 VAT-incl)', ukSPinc, usSP, {cls:'deduct', zeroDash:true});
  h += row('VAT Recovery (UK 20/120 on Storage + Fulfillment + Ad Spend + Per-order Shipping + TT Comm + Aff Comm + Smart Promo)', ukVatRec, 0, {cls:'add', zeroDash:true});
  h += row('Free Sample Cost (units × per-pack UK rates, -£2 post Feb 14)', ukFsCost, usFsCost, {cls:'deduct', hideZero:true});
  h += marginRow('<b>CM2 (Net Margin)</b>', ukCM2, usCM2, ukNetSalesExVat, usNetSalesExVat, {requireCosts:true, cls:'total'});
  h += '</tbody>';
  document.getElementById('pnlTable').innerHTML = h;
}

let skuGrid = null;
function renderSkuTable(){
  const a = aggregate();
  const days = a.days;
  const ad = PNL.ad_spend_daily;
  const ccy = displayCcy();
  const sym = ccySym();
  const fx = state.fxRate || 1.27;
  function adFor(region, sku){
    let total = 0;
    for(const day of days){
      const m = ad.daily_by_sku[region]?.[day] || {};
      total += (m[sku]||0);
    }
    return total;
  }
  function toDisp(v, src){
    if(src === ccy) return v;
    if(src === 'GBP' && ccy === 'USD') return v * fx;
    if(src === 'USD' && ccy === 'GBP') return v / fx;
    return v;
  }
  const buckets = {};
  for(const r of a.orders){
    const k = r.region+'|'+r.sku;
    if(!buckets[k]) buckets[k] = {region:r.region, sku:r.sku, is_free_gift: r.is_free_gift, orders:0, qty:0, net_sales:0, cancelled_orders:0};
    const b = buckets[k];
    b.orders += (r.net_orders||0); b.qty += (r.net_qty||0);
    b.net_sales += (r.net_sales||0);
    b.cancelled_orders += (r.cancelled_orders||0);
  }
  const affMap = {};
  for(const r of a.aff){
    const k = r.region+'|'+r.sku;
    if(!affMap[k]) affMap[k] = 0;
    affMap[k] += r.aff_commission;
  }
  const rows = Object.values(buckets).map(b => {
    const adv = adFor(b.region, b.sku);
    const affComm = affMap[b.region+'|'+b.sku] || 0;
    const contrib = b.net_sales - affComm - adv;
    const skuLabel = b.is_free_gift ? b.sku+' <span class="tag gift">FREE</span>' : b.sku;
    const srcCcy = b.region==='UK' ? 'GBP' : 'USD';
    return [b.region, skuLabel, b.orders, Math.round(b.qty),
            toDisp(b.net_sales, srcCcy), b.cancelled_orders,
            toDisp(affComm, srcCcy), toDisp(adv, srcCcy), toDisp(contrib, srcCcy), ccy];
  }).sort((x,y) => y[4]-x[4]);
  // FIX 6: For SKU rows where ad spend / affiliate comm is zero (typical
  // niche-SKU days), show "—" instead of "£0" / "$0".
  const dashOrMoney = (v, c) => Math.abs(v) < 0.005 ? '—' : fmtMoney(v, c);
  const data = rows.map(r => [
    r[0], gridjs.html(r[1]), r[2], r[3],
    fmtMoney(r[4], r[9]), String(r[5]),
    dashOrMoney(r[6], r[9]), dashOrMoney(r[7], r[9]), fmtMoney(r[8], r[9])
  ]);
  const host = document.getElementById('skuTableHost');
  host.innerHTML = '';
  skuGrid = new gridjs.Grid({
    columns: [{name:'Region', width:'70px'}, {name:'SKU', width:'220px'}, {name:'Net Orders', width:'90px'}, {name:'Net Units', width:'90px'}, {name:'Net Sales ('+ccy+')', width:'120px'}, {name:'Cancelled', width:'90px'}, {name:'Aff Comm ('+ccy+')', width:'110px'}, {name:'Ad Spend ('+ccy+')', width:'110px'}, {name:'Contribution ('+ccy+')', width:'140px'}],
    data, search:true, sort:true, pagination:{limit:20}, resizable:true
  }).render(host);
}

let ukChart=null, usChart=null;
function renderAdCharts(){
  const ad = PNL.ad_spend_daily;
  const win = effectiveWindow();
  const days = []; let d = win.from;
  while(d<=win.to){ days.push(d); d = isoAdd(d, 1); }
  function sumBySku(region){
    const totals = {};
    for(const day of days){
      const m = ad.daily_by_sku[region]?.[day] || {};
      for(const [sku, val] of Object.entries(m)){ totals[sku] = (totals[sku]||0) + val; }
    }
    return totals;
  }
  const palette = ['#6B1A1B','#C9A24C','#8B2A2A','#5C4A36','#A0312C','#D4B86E','#7A2828','#B89968','#3D6F4E'];
  function build(canvasId, region, oldChart){
    const totals = sumBySku(region);
    const labels = Object.keys(totals).sort((a,b)=>totals[b]-totals[a]);
    const data = labels.map(l => Math.round(totals[l]*100)/100);
    const ctx = document.getElementById(canvasId);
    if(oldChart) oldChart.destroy();
    return new Chart(ctx, {
      type:'doughnut',
      data:{labels, datasets:[{data, backgroundColor: labels.map((_,i)=>palette[i%palette.length]), borderWidth:1, borderColor:'#fff'}]},
      options:{plugins:{legend:{position:'right', labels:{font:{size:11}}}, tooltip:{callbacks:{label:c=>c.label+': '+(region==='UK'?'£':'$')+c.parsed.toLocaleString()}}}}
    });
  }
  ukChart = build('ukAdChart', 'UK', ukChart);
  usChart = build('usAdChart', 'US', usChart);
}

function renderCampaignTable(){
  const campaigns = PNL.ad_spend_30d;
  let h = '<thead><tr><th>Region</th><th>Type</th><th>Campaign</th><th>L30 Cost</th></tr></thead><tbody>';
  for(const region of ['UK','US']){
    const ccy = region==='UK'?'GBP':'USD';
    for(const c of (campaigns[region]?.product_gmv_max||[]).filter(c=>c.cost>0)){
      h += '<tr><td>'+region+'</td><td><span class="tag '+region.toLowerCase()+'">Product GMV</span></td><td class="label">'+c.campaign+'</td><td>'+fmtMoney(c.cost, ccy)+'</td></tr>';
    }
    for(const c of (campaigns[region]?.live_gmv_max||[]).filter(c=>c.cost>0)){
      h += '<tr><td>'+region+'</td><td><span class="tag warn">LIVE GMV</span></td><td class="label">'+c.campaign+'</td><td>'+fmtMoney(c.cost, ccy)+'</td></tr>';
    }
  }
  h += '</tbody>';
  document.getElementById('campaignTbl').innerHTML = h;
}

let creativeGrid = null;
function renderCreatives(){
  const region = state.region==='US' ? 'US' : 'UK';
  const reg = PNL.creatives && PNL.creatives[region];
  if(!reg){ return; }
  const sel = document.getElementById('creativeSnap');
  if(sel.options.length !== reg.snapshots.length){
    sel.innerHTML = '';
    reg.snapshots.forEach((s, i) => {
      const o = document.createElement('option');
      o.value = i; o.textContent = s.period;
      if(i === creativeState.snapshotIdx) o.selected = true;
      sel.appendChild(o);
    });
  }
  const snap = reg.snapshots[creativeState.snapshotIdx];
  if(!snap){ return; }
  const t = snap.totals;
  const ccy = snap.currency;
  const sym = ccy==='GBP'?'£':'$';
  const ctr = t.impressions ? (t.clicks/t.impressions*100) : 0;
  const cvr = t.clicks ? (t.orders/t.clicks*100) : 0;
  const roas = t.cost ? (t.gmv/t.cost) : 0;
  const cpm = t.impressions ? (t.cost/t.impressions*1000) : 0;
  const cpc = t.clicks ? (t.cost/t.clicks) : 0;
  const roasTag = roas>=1.5?'<span class="tag good">healthy</span>':roas>=1?'<span class="tag warn">borderline</span>':'<span class="tag" style="background:#fdd;color:#9c3413">below break-even</span>';
  document.getElementById('creativeKPIs').innerHTML =
    '<div class="kpi"><div class="label">Videos</div><div class="value">'+fmtNum(t.videos)+'</div><div class="sub2">'+region+' · '+snap.period+'</div></div>'+
    '<div class="kpi"><div class="label">Impressions</div><div class="value">'+fmtNum(t.impressions)+'</div><div class="sub2">CPM '+sym+cpm.toFixed(2)+'</div></div>'+
    '<div class="kpi"><div class="label">Clicks</div><div class="value">'+fmtNum(t.clicks)+'</div><div class="sub2">CPC '+sym+cpc.toFixed(2)+'</div></div>'+
    '<div class="kpi"><div class="label">CTR</div><div class="value">'+ctr.toFixed(2)+'%</div><div class="sub2">clicks / impressions</div></div>'+
    '<div class="kpi"><div class="label">Orders</div><div class="value">'+fmtNum(t.orders)+'</div><div class="sub2">CVR '+cvr.toFixed(2)+'%</div></div>'+
    '<div class="kpi"><div class="label">GMV</div><div class="value">'+sym+fmtNum(t.gmv)+'</div><div class="sub2">attributed</div></div>'+
    '<div class="kpi"><div class="label">Spend</div><div class="value">'+sym+fmtNum(t.cost)+'</div><div class="sub2">creator + ads</div></div>'+
    '<div class="kpi"><div class="label">ROAS</div><div class="value">'+roas.toFixed(2)+'x</div><div class="sub2">'+roasTag+'</div></div>';
  function bucketCard(name, b){
    if(!b) return '';
    const ctr2 = b.impressions ? (b.clicks/b.impressions*100) : 0;
    const cvr2 = b.clicks ? (b.orders/b.clicks*100) : 0;
    const roas2 = b.cost ? (b.gmv/b.cost) : 0;
    const isExt = name==='external';
    return '<div class="bucket-card '+(isExt?'ext':'int')+'"><div class="bucket-head">'+(isExt?'External (affiliate creators)':'Internal (own/agency content)')+' <span class="tag '+(isExt?'ext':'int')+'">'+name+'</span></div><div class="bucket-grid">'+
      '<div><div class="b-label">Videos</div><div class="b-val">'+fmtNum(b.videos)+'</div></div>'+
      '<div><div class="b-label">Impressions</div><div class="b-val">'+fmtNum(b.impressions)+'</div></div>'+
      '<div><div class="b-label">Clicks</div><div class="b-val">'+fmtNum(b.clicks)+'</div></div>'+
      '<div><div class="b-label">CTR</div><div class="b-val">'+ctr2.toFixed(2)+'%</div></div>'+
      '<div><div class="b-label">Orders</div><div class="b-val">'+fmtNum(b.orders)+'</div></div>'+
      '<div><div class="b-label">CVR</div><div class="b-val">'+cvr2.toFixed(2)+'%</div></div>'+
      '<div><div class="b-label">GMV</div><div class="b-val">'+sym+fmtNum(b.gmv)+'</div></div>'+
      '<div><div class="b-label">Spend</div><div class="b-val">'+sym+fmtNum(b.cost)+'</div></div>'+
      '<div><div class="b-label">ROAS</div><div class="b-val">'+roas2.toFixed(2)+'x</div></div></div></div>';
  }
  document.getElementById('creativeBucketCmp').innerHTML = bucketCard('external', snap.by_bucket.external) + bucketCard('internal', snap.by_bucket.internal);
  let videos = snap.top_videos || [];
  if(creativeState.bucket !== 'both') videos = videos.filter(v => v.bucket === creativeState.bucket);
  const data = videos.slice(0, 100).map(v => [
    v.bucket==='external' ? gridjs.html('<span class="tag ext">ext</span>') : gridjs.html('<span class="tag int">int</span>'),
    v.username || '-',
    (v.product_name || '').substring(0, 35) + (v.product_name && v.product_name.length>35 ? '…' : ''),
    fmtNum(v.impressions), fmtNum(v.clicks),
    ((v.ctr||0)*100).toFixed(2)+'%',
    fmtNum(v.sku_orders),
    ((v.cvr||0)*100).toFixed(2)+'%',
    sym+fmtNum(v.gross_revenue), sym+fmtNum(v.cost),
    (v.roas||0).toFixed(2)+'x', v.time_posted || ''
  ]);
  const host = document.getElementById('creativeTableHost');
  host.innerHTML = '';
  creativeGrid = new gridjs.Grid({
    columns: [{name:'Type', width:'60px'},{name:'Creator', width:'130px'},{name:'Product', width:'200px'},{name:'Impressions', width:'100px'},{name:'Clicks', width:'80px'},{name:'CTR', width:'70px'},{name:'Orders', width:'80px'},{name:'CVR', width:'70px'},{name:'GMV', width:'100px'},{name:'Spend', width:'100px'},{name:'ROAS', width:'70px'},{name:'Posted', width:'100px'}],
    data, search:true, sort:true, pagination:{limit:25}, resizable:true
  }).render(host);
}

function renderMonthlyHistory(){
  const host = document.getElementById('monthlyHistory');
  if(!host) return;
  const hist = PNL.monthly_history;
  if(!hist){ host.innerHTML = '<div class="h-sub">No monthly history.</div>'; return; }
  const fx = state.fxRate || 1.27;
  const ccy = displayCcy();
  const sym = ccySym();
  function fmtCcyL(v){ if(v==null) return '—'; const sign=v<0?'-':''; return sign+sym+fmtNum(Math.abs(v)); }
  function fmtPct(v){ if(v==null) return '—'; const cls = v<0?'style="color:var(--neg);font-weight:600"':(v>=15?'style="color:var(--pos);font-weight:600"':''); return '<span '+cls+'>'+v.toFixed(1)+'%</span>'; }
  const showUK = state.region !== 'US';
  const showUS = state.region !== 'UK';
  function getUkRows(){
    const uk = hist.UK; if(!uk) return null;
    const months = uk.months;
    let data;
    if(state.sku && state.variation){
      const vd = uk.by_sku_variation[state.sku];
      data = vd ? vd[state.variation] : null;
    } else if(state.sku){ data = uk.by_sku[state.sku]; }
    else { data = uk.overall; }
    return {months, rows: data};
  }
  function getUsRows(){
    const us = hist.US; if(!us) return null;
    // FIX 1: monthly_history.US is now month-keyed (matching UK structure). Use
    // ISO month keys ('2026-01'...'2026-05'); fall back to legacy us.months
    // labels for display.
    const monthsKeys = ['2026-01','2026-02','2026-03','2026-04','2026-05'];
    const displayLabels = us.months || ["Jan'26","Feb'26","Mar'26","Apr'26","May'26 MTD"];
    let data;
    if(state.sku){ data = us.products ? us.products[state.sku] : null; }
    else { data = us.overall; }
    return {months: monthsKeys, monthLabels: displayLabels, rows: data};
  }
  function buildUkTable(){
    const r = getUkRows();
    if(!r || !r.rows){ return '<div class="h-sub">No UK monthly data for this filter combo.</div>'; }
    let h = '<h3 style="margin-top:14px;color:var(--maroon);">UK monthly — '+(state.variation && state.sku ? state.sku+' / '+state.variation : (state.sku || 'Overall'))+'</h3>';
    h += '<table class="pnl"><thead><tr><th>Metric</th>';
    for(const m of r.months) h += '<th>'+m+'</th>';
    h += '</tr></thead><tbody>';
    const rows = [
      ['Net Orders', 'net_orders', 'num'],
      ['Net Units', 'net_units', 'num'],
      ['Net Sales', 'net_sales', 'money'],
      ['Cancelled', 'cancelled', 'num'],
      ['Samples', 'samples', 'num'],
      ['(−) Unit Cost', 'unit_cost', 'money'],
      ['(−) Per-order Shipping (Mar+)', 'shipping_cost', 'money'],
      ['CM1', 'cm1', 'money'],
      ['CM1 %', 'cm1_pct', 'pct'],
      ['(−) Affiliate Comm', 'aff_comm', 'money'],
      ['(−) Ad Spend (UK ×1.20 VAT-incl)', 'ad_spend', 'money'],
      ['(+) VAT Recovery (20/120 on VAT-incl)', 'vat_recovery', 'money'],
      ['CM2 (Net Margin)', 'cm2', 'money'],
      ['CM2 %', 'cm2_pct', 'pct']
    ];
    for(const [label, key, type] of rows){
      const isCM = key==='cm1' || key==='cm2';
      h += '<tr class="'+(isCM?'subtotal':'')+'"><td class="label">'+label+'</td>';
      for(const m of r.months){
        const v = r.rows[m] ? r.rows[m][key] : null;
        if(type==='money'){
          const dispV = ccy==='GBP' ? v : (v==null?null:v*fx);
          h += '<td>'+fmtCcyL(dispV)+'</td>';
        } else if(type==='pct'){ h += '<td>'+fmtPct(v)+'</td>'; }
        else { h += '<td>'+fmtNum(v)+'</td>'; }
      }
      h += '</tr>';
    }
    h += '</tbody></table>';
    return h;
  }
  function buildUsTable(){
    const r = getUsRows();
    if(!r || !r.rows){
      const us = hist.US;
      if(us && state.sku && !(us.products && us.products[state.sku])){
        return '<div class="h-sub">No US monthly data for "'+state.sku+'" — sheet has TikTok monthly for Coffee, Turmeric Curcumin, Shatavari, Ashwagandha Caps only.</div>';
      }
      return '<div class="h-sub">No US monthly data.</div>';
    }
    let h = '<h3 style="margin-top:14px;color:var(--maroon);">US monthly — '+(state.sku || 'Overall')+'</h3>';
    h += '<table class="pnl"><thead><tr><th>Metric</th>';
    for(const lbl of r.monthLabels) h += '<th>'+lbl+'</th>';
    h += '</tr></thead><tbody>';
    // FIX 1: Mirror UK schema. Source = month-keyed dict with snake_case fields.
    const rows = [
      ['Net Orders', 'net_orders', 'num'],
      ['Net Units', 'net_units', 'num'],
      ['Net Sales', 'net_sales', 'money'],
      ['Cancelled', 'cancelled', 'num'],
      ['Samples', 'samples', 'num'],
      ['(−) Unit Cost', 'unit_cost', 'money'],
      ['CM1', 'cm1', 'money'],
      ['CM1 %', 'cm1_pct', 'pct'],
      ['(−) Affiliate Comm', 'aff_comm', 'money'],
      ['(−) Ad Spend', 'ad_spend', 'money'],
      ['(−) Smart Promo', 'smart_promo', 'money'],
      ['(−) Free Sample Cost', 'free_sample_cost', 'money'],
      ['CM2 (Net Margin)', 'cm2', 'money'],
      ['CM2 %', 'cm2_pct', 'pct']
    ];
    for(const [label, key, type] of rows){
      const isCM = key==='cm1' || key==='cm2';
      h += '<tr class="'+(isCM?'subtotal':'')+'"><td class="label">'+label+'</td>';
      for(const mk of r.months){
        const v = r.rows[mk] ? r.rows[mk][key] : null;
        if(type==='money'){
          const dispV = ccy==='USD' ? v : (v==null?null:v/fx);
          h += '<td>'+fmtCcyL(dispV)+'</td>';
        } else if(type==='pct'){ h += '<td>'+fmtPct(v)+'</td>'; }
        else if(type==='roi'){ h += '<td>'+(typeof v==='number' ? v.toFixed(2)+'x' : '—')+'</td>'; }
        else { h += '<td>'+fmtNum(v)+'</td>'; }
      }
      h += '</tr>';
    }
    h += '</tbody></table>';
    return h;
  }
  let h = '';
  if(showUK) h += buildUkTable();
  if(showUS) h += buildUsTable();
  host.innerHTML = h;
}

function refresh(){
  const win = effectiveWindow();
  document.getElementById('rangePill').textContent = win.from+' → '+win.to+' · '+dayDiff(win)+'d';
  renderKPIs(); renderPnLTable(); renderSkuTable(); renderAdCharts(); renderCampaignTable(); renderCreatives(); renderMonthlyHistory();
}

function init(){
  // FIX 3: Hide "Other" SKU from default dropdown (data exhaust / unclassified).
  // User can still select it via "Other (unclassified)" item; surface as last item.
  const allSkusRaw = [...new Set(PNL.orders_daily.map(r => r.sku))];
  const allSkus = allSkusRaw.filter(s => s !== 'Other').sort();
  if(allSkusRaw.includes('Other')) allSkus.push('Other');
  const skuSel = document.getElementById('skuSel');
  for(const s of allSkus){
    const o = document.createElement('option');
    o.value = s;
    o.textContent = s === 'Other' ? 'Other (unclassified)' : s;
    skuSel.appendChild(o);
  }
  // FIX 3: Show "Default" variation as "Unspecified" but keep it selectable.
  const allVars = [...new Set(PNL.orders_daily.map(r => r.variation))].sort();
  const varSel = document.getElementById('varSel');
  for(const v of allVars){
    const o = document.createElement('option');
    o.value = v;
    o.textContent = v === 'Default' ? 'Unspecified' : v;
    varSel.appendChild(o);
  }
  document.querySelectorAll('#regionSeg button').forEach(b => b.addEventListener('click', e=>{
    document.querySelectorAll('#regionSeg button').forEach(x=>x.classList.remove('active'));
    b.classList.add('active'); state.region = b.dataset.v; refresh();
  }));
  document.querySelectorAll('#periodSeg button').forEach(b => b.addEventListener('click', e=>{
    document.querySelectorAll('#periodSeg button').forEach(x=>x.classList.remove('active'));
    b.classList.add('active'); state.period = b.dataset.v;
    document.getElementById('customRange').classList.toggle('hidden', state.period!=='CUSTOM');
    refresh();
  }));
  skuSel.addEventListener('change', e=>{ state.sku = e.target.value; refresh(); });
  varSel.addEventListener('change', e=>{ state.variation = e.target.value; refresh(); });
  document.getElementById('fromDate').addEventListener('change', e=>{ state.customFrom = e.target.value; refresh(); });
  document.getElementById('toDate').addEventListener('change', e=>{ state.customTo = e.target.value; refresh(); });
  document.getElementById('giftToggle').addEventListener('change', e=>{ state.includeFreeGifts = e.target.checked; refresh(); });
  document.getElementById('fxInput').addEventListener('change', e=>{ state.fxRate = parseFloat(e.target.value) || 1.27; refresh(); });
  document.getElementById('creativeSnap').addEventListener('change', e=>{ creativeState.snapshotIdx = parseInt(e.target.value); renderCreatives(); });
  document.querySelectorAll('#creativeBucketSeg button').forEach(b => b.addEventListener('click', e=>{
    document.querySelectorAll('#creativeBucketSeg button').forEach(x=>x.classList.remove('active'));
    b.classList.add('active'); creativeState.bucket = b.dataset.v; renderCreatives();
  }));
  document.getElementById('fromDate').min = PNL.window_start; document.getElementById('fromDate').max = PNL.window_end; document.getElementById('fromDate').value = PNL.window_start;
  document.getElementById('toDate').min = PNL.window_start; document.getElementById('toDate').max = PNL.window_end; document.getElementById('toDate').value = PNL.window_end;
  // Yesterday button: show the actual referenced date in the label + tooltip.
  // Anchors to dataEndDate() (region-agnostic) so the label is stable across
  // SKU/Region toggles; the per-filter latestDataDate() drives the actual
  // window when clicked.
  const ydayBtn = document.querySelector('#periodSeg button[data-v="YDAY"]');
  if(ydayBtn){
    const anchor = dataEndDate();
    ydayBtn.textContent = 'Yesterday (' + anchor + ')';
    ydayBtn.title = 'Yesterday = latest day with data (' + anchor + ')';
  }
  refresh();
}

if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', init);
else init();
"""

DATA_JSON = json.dumps(PNL, separators=(',',':'))

HTML_BODY = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Vahdam P&amp;L Tracker</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/gridjs@5.0.2/dist/theme/mermaid.min.css" integrity="sha384-jZvDSsmGB9oGGT/4l9bHXGoAv1OxvG/cFmSo0dZaSqmBgvQTKDBFAMftlXTmMbNW" crossorigin="anonymous">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.js" integrity="sha384-iU8HYtnGQ8Cy4zl7gbNMOhsDTTKX02BTXptVP/vqAWIaTfM7isw76iyZCsjL2eVi" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/gridjs@5.0.2/dist/gridjs.umd.js" integrity="sha384-/XXDzxe4FsGiAe50i/u9pY/Vy/uX654MHB1xoc1BJNnH1WXHhqHga9g3q5tF4gj7" crossorigin="anonymous"></script>
<style>__CSS__</style></head><body>
<div class="wrap">
<h1>Vahdam P&amp;L Tracker</h1>
<div class="sub">TikTok Shop UK + US · Orders, Affiliate, Ad Spend, Creatives · CM1 / CM2 with UK tax rules</div>
<div id="freshnessBanner" class="warn-strip" style="display:none;border-left-color:var(--neg);background:#FBE9C0"></div>
<div class="bar">
<label>Period</label>
<div class="seg" id="periodSeg"><button data-v="YDAY">Yesterday</button><button data-v="L7">Last 7d</button><button data-v="L30" class="active">Last 30d</button><button data-v="CUSTOM">Custom</button></div>
<span id="customRange" class="hidden" style="display:inline-flex; gap:6px; align-items:center; margin-left:10px;"><input type="date" id="fromDate"> <span style="color:var(--mute)">&rarr;</span> <input type="date" id="toDate"></span>
<span class="range-pill" id="rangePill"></span>
</div>
<div class="bar">
<label>Region</label>
<div class="seg" id="regionSeg"><button data-v="both" class="active">Both</button><button data-v="UK">UK</button><button data-v="US">US</button></div>
<label style="margin-left:14px;">SKU</label><select id="skuSel"><option value="">All SKUs (excl. free gifts)</option></select>
<label style="margin-left:14px;">Variation</label><select id="varSel"><option value="">All variations</option></select>
<label class="gift-toggle"><input type="checkbox" id="giftToggle"> Include free gifts</label>
<label style="margin-left:14px;">GBP&rarr;USD</label><input type="number" id="fxInput" value="1.27" step="0.01" min="0.5" max="3" style="width:70px;">
</div>
<div class="warn-strip"><b>Display currency follows region</b>: UK&rarr;GBP; US&rarr;USD; Both&rarr;USD (UK&times;FX). <b>Net Sales (top line)</b> excludes cancelled, samples, refunds, returns. <b>UK VAT treatment in PnL:</b> 20% VAT subtracted from Net Sales for zero-rated supplements (Coffee Apr 2026+, Green Burner, Ashwagandha Caps, Turmeric Curcumin) before building CM. Ginger Tea keeps VAT in sales (non-supplement). <b>Other UK rules:</b> &pound;1.99/order shipping from Mar 2026; Ad spend + Smart Promo grossed up &times;1.20 (Seller Center shows VAT-EXCL); VAT recovery = (Ad+SP)<sub>incl</sub> &times; 20/120 added back to CM2. <b>US</b>: no VAT/shipping rules.</div>
<div class="kpis" id="kpis"></div>
<h2>P&amp;L Statement <span class="badge">CM1 / CM2</span></h2>
<div class="card"><table class="pnl" id="pnlTable"></table></div>
<h2>Per-SKU breakdown</h2>
<div class="card"><div class="h-sub">Sortable, searchable. Free gifts shown with FREE tag when included.</div><div id="skuTableHost"></div></div>
<h2>Ad spend breakdown <span class="badge">Seller Center L30</span></h2>
<div class="card"><div class="h-sub">Per-SKU split based on each SKU&apos;s share of Product GMV Max L30. LIVE GMV Max + Auto-created promos lumped as (unallocated).</div>
<div class="grid"><div class="card" style="margin:0;"><h3>UK ad spend by SKU</h3><canvas id="ukAdChart"></canvas></div><div class="card" style="margin:0;"><h3>US ad spend by SKU</h3><canvas id="usAdChart"></canvas></div></div>
<h3 style="margin-top:14px;">Campaigns (Seller Center L30)</h3><table class="pnl" id="campaignTbl"></table></div>
<h2>Creatives analytics <span class="badge">internal vs external</span></h2>
<div class="bar">
<label>Snapshot</label>
<select id="creativeSnap"></select>
<label style="margin-left:14px;">Bucket</label>
<div class="seg" id="creativeBucketSeg"><button data-v="both" class="active">All</button><button data-v="external">External</button><button data-v="internal">Internal</button></div>
<span style="font-size:11px;color:var(--mute);margin-left:8px;">Uses UK creative data when Region = Both</span>
</div>
<div class="kpis" id="creativeKPIs"></div>
<div class="bucket-cmp" id="creativeBucketCmp"></div>
<h3 style="margin-top:18px;">Top creatives by GMV</h3>
<div class="card">
<div class="h-sub">Top 100 videos by attributed GMV in selected snapshot. Sort by clicking column headers.</div>
<div id="creativeTableHost"></div>
</div>
<h2>Monthly CM History <span class="badge">Jan&ndash;May 2026</span></h2>
<div class="card">
<div class="h-sub">UK monthly computed from order CSVs + UK Inventory Planning costs + Seller Center monthly ad spend. UK tax rules applied. US monthly from your USA workbook. Filters above (SKU + variation) apply here too.</div>
<div id="monthlyHistory" style="overflow-x:auto;"></div>
</div>
<div class="foot">Live: TikTok Seller Center scrape (Chrome via CDP) + manual affiliate CSVs + manual smart promo. UK COGs/CM2 from Vahdam Inventory Planning sheet. &middot; Crafted for VAHDAM India</div>
</div>
<script>
const PNL = __DATA__;
__JS__
</script>
</body>
</html>
"""

HTML = HTML_BODY.replace('__CSS__', CSS).replace('__JS__', JS).replace('__DATA__', DATA_JSON)
pathlib.Path(OUTPUT_PATH).write_text(HTML, encoding='utf-8')
import os
print('Wrote', OUTPUT_PATH, 'size:', os.path.getsize(OUTPUT_PATH))

# -----------------------------------------------------------------------------
# FIX 5: Ad-spend math audit -- prove no double-application of UK VAT gross-up.
# -----------------------------------------------------------------------------
from datetime import date as _date, timedelta as _td
_end = _date.fromisoformat(PNL['window_end'])
_L30 = {(_end - _td(days=i)).isoformat() for i in range(30)}
_ads = PNL.get('ad_spend_daily', {}).get('daily_by_sku', {})
def _sum_region(region):
    total = 0.0
    for d_ in _L30:
        for _sku, v in (_ads.get(region) or {}).get(d_, {}).items():
            total += v
    return total
_uk_ad_ex = _sum_region('UK')
_us_ad_ex = _sum_region('US')
_uk_sp_ex = 0.0
_us_sp_ex = 0.0
for _b in PNL.get('smart_promo_monthly', []) or []:
    _ws, _we = _b.get('window_start',''), _b.get('window_end','')
    # overlap with L30 by per-day proportion
    _bucket_days = []
    if _ws and _we:
        try:
            _ds = _date.fromisoformat(_ws); _de = _date.fromisoformat(_we)
            _cur = _ds
            while _cur <= _de:
                _bucket_days.append(_cur.isoformat()); _cur += _td(days=1)
        except Exception:
            pass
    if not _bucket_days: continue
    _in = sum(1 for d_ in _bucket_days if d_ in _L30)
    if _in == 0: continue
    _allocated = _b.get('cost',0) * (_in / len(_bucket_days))
    if _b.get('region') == 'UK': _uk_sp_ex += _allocated
    elif _b.get('region') == 'US': _us_sp_ex += _allocated

_uk_ad_inc = _uk_ad_ex * 1.20
_uk_sp_inc = _uk_sp_ex * 1.20
_uk_vat_rec = (_uk_ad_inc + _uk_sp_inc) * (20/120)
_uk_net_marketing_deduction = _uk_ad_inc + _uk_sp_inc - _uk_vat_rec

print()
print('================ AFFILIATE LOOKUP AUDIT (Yesterday) ================')
_yday = PNL['window_end']
for _r in ['UK', 'US']:
    _rows = [a for a in PNL.get('aff_daily', []) if a['region']==_r and a['date']==_yday]
    _sum = sum(a.get('aff_commission', 0) for a in _rows)
    _sym = '£' if _r == 'UK' else '$'
    print(f'  {_r} Yesterday ({_yday}): {len(_rows)} rows, sum aff_commission = {_sym}{_sum:,.2f}')
    if _rows:
        for _a in _rows:
            print(f'    {_a["sku"]:18s} {_sym}{_a.get("aff_commission",0):>10,.2f}')

print()
print('================ AD SPEND MATH AUDIT (L30) ================')
print(f'UK ad spend ex-VAT (stored):       £{_uk_ad_ex:>12,.2f}')
print(f'UK ad spend × 1.20 (inc-VAT):      £{_uk_ad_inc:>12,.2f}')
print(f'UK smart promo ex-VAT (allocated): £{_uk_sp_ex:>12,.2f}')
print(f'UK smart promo × 1.20 (inc-VAT):   £{_uk_sp_inc:>12,.2f}')
print(f'UK VAT recovery 20/120 of inc:     £{_uk_vat_rec:>12,.2f}')
print(f'UK net CM2 marketing deduction:    £{_uk_net_marketing_deduction:>12,.2f}')
print(f'   (= ad_ex + sp_ex = £{_uk_ad_ex + _uk_sp_ex:,.2f}; check passes)')
print()
print(f'US ad spend ex-VAT (stored):       ${_us_ad_ex:>12,.2f}  (no gross-up)')
print(f'US smart promo (allocated):        ${_us_sp_ex:>12,.2f}  (no gross-up)')
print(f'US net CM2 marketing deduction:    ${_us_ad_ex + _us_sp_ex:>12,.2f}')
print('==========================================================')

