--
-- PostgreSQL database dump
--

-- Dumped from database version 13.5 (Debian 13.5-0+deb11u1)
-- Dumped by pg_dump version 13.5 (Debian 13.5-0+deb11u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: tablefunc; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS tablefunc WITH SCHEMA public;


--
-- Name: EXTENSION tablefunc; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION tablefunc IS 'functions that manipulate whole tables, including crosstab';


--
-- Name: br_t(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.br_t() RETURNS TABLE(activator character, rda character, mode character, band character, callsigns integer)
    LANGUAGE plpgsql
    AS $$
declare activator_row record;
	
begin
for activator_row in 
    select distinct activators.activator from activators
        union
        select distinct qso.activator from qso where qso.activator is not null
loop
    for activator, rda, mode, band, callsigns
 in
      select qso.activator, qso.rda, qso.mode, qso.band, count(distinct (qso.callsign, qso.dt)) as callsigns from
          (select activators.activator, qso.rda, qso.mode, qso.band, qso.callsign, qso.dt 
              from qso join activators on qso.upload_id = activators.upload_id
              where activators.activator = activator_row.activator
                  union all
              select qso.activator, qso.rda, qso.mode, qso.band, qso.callsign, qso.dt from qso
              where qso.activator = activator_row.activator) as qso
              group by qso.activator, qso.rda, qso.mode, qso.band
    loop
        return next;
    end loop;
end loop;
return;
end
$$;


ALTER FUNCTION public.br_t() OWNER TO postgres;

--
-- Name: br_t0(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.br_t0() RETURNS void
    LANGUAGE plpgsql
    AS $$
declare activator_row record;
	
begin
for activator_row in 
    select distinct activators.activator from activators
        union
        select distinct qso.activator from qso where qso.activator is not null
loop
	insert into ra_t (activator, rda, mode, band, callsigns)
		select qso.activator, qso.rda, qso.mode, qso.band, count(distinct (qso.callsign, qso.dt)) as callsigns from
		  (select activators.activator, qso.rda, qso.mode, qso.band, qso.callsign, qso.dt 
			  from qso join activators on qso.upload_id = activators.upload_id
			  where activators.activator = activator_row.activator
				  union all
			  select qso.activator, qso.rda, qso.mode, qso.band, qso.callsign, qso.dt from qso
			  where qso.activator = activator_row.activator) as qso
			  group by qso.activator, qso.rda, qso.mode, qso.band;
end loop;
end
$$;


ALTER FUNCTION public.br_t0() OWNER TO postgres;

--
-- Name: build_activators_rating(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.build_activators_rating() RETURNS void
    LANGUAGE plpgsql
    AS $$
declare 
	activator_row record;
begin
RAISE LOG 'build_activators_raiting start';
delete from activators_rating;
delete from activators_rating_detail;
for activator_row in 
    select distinct activators.activator from activators
        union
        select distinct qso.activator from qso where qso.activator is not null
loop
	insert into activators_rating_detail (activator, qso_year, rda, points, mult)
		select activator, qso_year, rda, sum(qso_count) as points, count(*) filter (where qso_count > 49) as mult from 
			(select activator, rda, band, qso_year, count(distinct (callsign, mode)) as qso_count from
				(select activators.activator, qso.rda, qso.band, qso.mode, qso.callsign, extract(year from qso.dt) as qso_year
			  		from qso join activators on qso.upload_id = activators.upload_id
			  		where (station_callsign like '%/M' or station_callsign like '%/P') and activators.activator = activator_row.activator
				union all
			  	select qso.activator, qso.rda, qso.band, qso.mode, qso.callsign, extract(year from qso.dt) as qso_year from qso
			  		where (station_callsign like '%/M' or station_callsign like '%/P') and activator = activator_row.activator
				) as qsos
				group by activator, rda, band, qso_year) as rda_qsos
			group by activator, rda, qso_year
		 	having count(*) filter (where qso_count > 49) > 0;
	insert into activators_rating (activator, qso_year, rating)
		select activator_row.activator, qso_year, sum(points * mult) * count(*) as rating 
			from activators_rating_detail
			where activator = activator_row.activator
			group by qso_year;	
end loop;

RAISE LOG 'build_activators_raiting finish';
end;
$$;


ALTER FUNCTION public.build_activators_rating() OWNER TO postgres;

--
-- Name: build_rankings(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.build_rankings() RETURNS void
    LANGUAGE plpgsql
    AS $$
declare 
	activator_row record;
	_9band_tr smallint;

begin
RAISE LOG 'build_rankings: start';
-- rda
/*
delete from rda_activator;
delete from rda_hunter 
where 1 not in (select 1 from qso 
        where qso.callsign = hunter and qso.mode = rda_hunter.mode and 
            qso.band = rda_hunter.band and qso.rda = rda_hunter.rda);
RAISE LOG 'build_rankings: rda tables were purged';
*/
/*
insert into rda_hunter (hunter, mode, band, rda)
WITH RECURSIVE cte AS (
   (   -- parentheses required
   SELECT callsign, mode, band, rda
   FROM   qso
   ORDER  BY 1
   LIMIT  1
   )
   UNION ALL
   SELECT l.*
   FROM   cte c
   CROSS  JOIN LATERAL (
      SELECT callsign, mode, band, rda
      FROM   qso q
      WHERE  q.callsign > q.callsign or 
	   	(q.callsign = c.callsign and q.mode > c.mode) or  -- lateral reference
	    (q.callsign = c.callsign and q.mode = c.mode and q.band > c.band) or 
	    (q.callsign = c.callsign and q.mode = c.mode and q.band = c.band and q.rda > c.rda)
      ORDER  BY 1
      LIMIT  1
      ) l
   ) table cte
on conflict on constraint rda_hunter_uq do nothing;

insert into rda_hunter (hunter, mode, band, rda)
select distinct callsign, mode, band, rda from qso
on conflict on constraint rda_hunter_uq do nothing;

RAISE LOG 'build_rankings: rda_hunter was built';
*/
for activator_row in 
    select distinct activators.activator from activators
        union
        select distinct qso.activator from qso where qso.activator is not null
loop
	insert into rda_activator (activator, rda, mode, band, callsigns)
		select qso.activator, qso.rda, qso.mode, qso.band, count(distinct (qso.callsign, qso.dt)) as callsigns from
		  (select activators.activator, qso.rda, qso.mode, qso.band, qso.callsign, qso.dt 
			  from qso join activators on qso.upload_id = activators.upload_id
			  where activators.activator = activator_row.activator
				  union all
			  select qso.activator, qso.rda, qso.mode, qso.band, qso.callsign, qso.dt from qso
			  where qso.activator = activator_row.activator) as qso
			  group by qso.activator, qso.rda, qso.mode, qso.band;
end loop;
RAISE LOG 'build_rankings: rda_activator was built';

insert into rda_hunter
select activator, rda, band, mode
from rda_activator
where callsigns > 49
on conflict on constraint rda_hunter_uq do nothing;

insert into rda_hunter
select activator, rda, band, null
from
(select activator, rda, band
from rda_activator
group by activator, rda, band
having sum(callsigns) > 49) as rda_activator_tm
on conflict on constraint rda_hunter_uq do nothing;

insert into rda_hunter
select activator, rda, null, null
from
(select activator, rda
from rda_activator
group by activator, rda
having sum(callsigns) > 99) as rda_activator_tt
where not exists
(select 1 from rda_hunter where hunter = activator and rda_hunter.rda = rda_activator_tt.rda);

RAISE LOG 'build_rankings: activators data was appended to rda_hunter';
-- rankings 

delete from rankings;

with rda_act_m_b as 
(select activator, mode, band, rda
from rda_activator
where callsigns > 49),

act_m_b as 
(select activator, mode, band, count(rda), rank() over w, row_number() over w
from rda_act_m_b
group by activator, mode, band
window w as (partition by mode, band order by count(rda) desc)),

act_t_b as
(select activator, band, count(rda), rank() over w, row_number() over w 
from
(select activator, rda, band
from rda_activator
group by activator, rda, band
having sum(callsigns) > 49) as act_total_band_f
group by activator, band
window w as (partition by band order by count(rda) desc)),

hnt_t_b as 
(select 'hunter', 'total', band, hunter, count(distinct rda), rank() over w, row_number() over w
from rda_hunter
where band is not null
group by hunter, band
window w as (partition by band order by count(distinct rda) desc))

insert into rankings

-- ACTIVATORS --

-- mode, band
select 'activator', mode, band, activator, count, rank, row_number from act_m_b 

union all

-- mode, bandsSum
select 'activator', mode, 'bandsSum', activator, sum(count), rank() over w, row_number() over w 
from act_m_b
group by activator, mode
window w as (partition by mode order by sum(count) desc)

union all

-- mode, total
select 'activator', mode, 'total', activator, count(rda), rank() over w, row_number() over w 
from
(select activator, mode, rda
from rda_activator
group by activator, mode, rda
having sum(callsigns) > 99) as act_m_total_f
group by activator, mode
window w as (partition by mode order by count(rda) desc)

union all
-- total, total
select 'activator', 'total', 'total', activator, count(rda), rank() over w, row_number() over w 
from
(select activator, rda
from rda_activator
group by activator, rda
having sum(callsigns) > 99) as act_total_total_f
group by activator
window w as (order by count(rda) desc)

union all
-- total, bandsSum
select 'activator', 'total', 'bandsSum', activator, sum(count), rank() over w, row_number() over w 
from act_t_b
group by activator
window w as (order by sum(count) desc)

union all
--total, band
select 'activator', 'total', band, activator, count, rank, row_number
from act_t_b

--- HUNTERS ---

union all
--mode, band
select 'hunter', mode, band, hunter, count(*), rank() over w, row_number() over w 
from rda_hunter
where mode is not null and band is not null
group by hunter, mode, band
window w as (partition by mode, band order by count(*) desc)

union all
--mode, bandsSum
select 'hunter', mode, 'bandsSum', hunter, count(*), rank() over w, row_number() over w 
from rda_hunter
where mode is not null
group by hunter, mode
window w as (partition by mode order by count(*) desc)

union all
--mode, total
select 'hunter', mode, 'total', hunter, count(distinct rda), rank() over w, row_number() over w 
from rda_hunter
where mode is not null
group by hunter, mode
window w as (partition by mode order by count(distinct rda) desc)

union all
--total, total
select 'hunter', 'total', 'total', hunter, count(distinct rda), rank() over w, row_number() over w 
from rda_hunter
where band is not null
group by hunter
window w as (order by count(distinct rda) desc)

union all
--total, band
select 'hunter', 'total', band, hunter, count, rank, row_number
from hnt_t_b

union all
--total, bandsSum 
select 'hunter', 'total', 'bandsSum', hunter, sum(count), rank() over w, row_number() over w
from hnt_t_b
group by hunter
window w as (order by sum(count) desc)

--- 9BANDS ---

union all

select 'hunter', 'total', '9BAND', hunter, sum(points), rank() over w, row_number() over w from
(select hunter, band, least(100, count(distinct rda)) as points
from rda_hunter
where band is not null
group by hunter, band) as s
group by hunter
window w as (order by sum(points) desc);

RAISE LOG 'build_rankings: main rankings are ready';

-- countries
insert into callsigns_countries (callsign, country_id)
select distinct rankings.callsign, 
	(select country_id 
	 	from country_prefixes 
	 	where rankings.callsign like prefix || '%'
		order by character_length(prefix) desc 
	 	limit 1) 
from rankings left join callsigns_countries on rankings.callsign = callsigns_countries.callsign
where callsigns_countries.callsign is null;

RAISE LOG 'build_rankings: countries callsigns were assigned';
--- 9BANDS 900+---

_9band_tr = 100;

while exists (select callsign from rankings where role = 'hunter' and mode = 'total' and band = '9BAND' and _count = 9*_9band_tr)
  loop
   update rankings set _count = new_count, _rank = new_rank, _row = new_row
   from
    (select hunter, sum(points) as new_count, rank() over w as new_rank, row_number() over w as new_row 
    from
      (select hunter, band, least(_9band_tr + 100, count(distinct rda)) as points
      from rda_hunter
      where band is not null and hunter in (select callsign from rankings where role = 'hunter' and mode = 'total' and band = '9BAND' and _count = 9*_9band_tr)
      group by hunter, band) as s
    group by hunter
    window w as (order by sum(points) desc)) as p2
   where callsign = hunter and role = 'hunter' and mode = 'total' and band = '9BAND';
  _9band_tr = _9band_tr + 100;
end loop;

RAISE LOG 'build_rankings: 9bands loop is finished';

--- country rankings---
update rankings as r set country_rank = cr._rank, country_row = cr._row
from
(select role, mode, band, rankings.callsign, country_id, _count, rank() over w as _rank, 
	row_number() over w as _row from rankings join callsigns_countries on rankings.callsign = callsigns_countries.callsign 
	window w as (partition by role, mode, band, country_id order by _count desc)
	order by _row) as cr
where r.role = cr.role and r.mode = cr.mode and r.band = cr.band and r.callsign = cr.callsign;

RAISE LOG 'build_rankings: counries rankings are ready';

end
$$;


ALTER FUNCTION public.build_rankings() OWNER TO postgres;

--
-- Name: build_rankings_activator_data(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.build_rankings_activator_data() RETURNS void
    LANGUAGE plpgsql
    AS $$declare 
	activator_row record;
begin
RAISE LOG 'build_rankings: activator data build up start';
for activator_row in 
    select distinct activators.activator from activators
        union
        select distinct qso.activator from qso where qso.activator is not null
loop
	insert into rda_activator (activator, rda, mode, band, callsigns)
		select qso.activator, qso.rda, qso.mode, qso.band, count(distinct (qso.callsign, qso.dt)) as callsigns from
		  (select activators.activator, qso.rda, qso.mode, qso.band, qso.callsign, qso.dt 
			  from qso join activators on qso.upload_id = activators.upload_id
			  where activators.activator = activator_row.activator
				  union all
			  select qso.activator, qso.rda, qso.mode, qso.band, qso.callsign, qso.dt from qso
			  where qso.activator = activator_row.activator) as qso
			  group by qso.activator, qso.rda, qso.mode, qso.band;
end loop;
RAISE LOG 'build_rankings: rda_activator was built';

insert into rda_hunter
select activator, rda, band, mode
from rda_activator
where callsigns > 49
on conflict on constraint rda_hunter_uq do nothing;

insert into rda_hunter
select activator, rda, band, null
from
(select activator, rda, band
from rda_activator
group by activator, rda, band
having sum(callsigns) > 49) as rda_activator_tm
on conflict on constraint rda_hunter_uq do nothing;

insert into rda_hunter
select activator, rda, null, null
from
(select activator, rda
from rda_activator
group by activator, rda
having sum(callsigns) > 99) as rda_activator_tt
where not exists
(select 1 from rda_hunter where hunter = activator and rda_hunter.rda = rda_activator_tt.rda);

RAISE LOG 'build_rankings: activators data was merged with rda_hunter';
end;$$;


ALTER FUNCTION public.build_rankings_activator_data() OWNER TO postgres;

--
-- Name: build_rankings_countries(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.build_rankings_countries() RETURNS void
    LANGUAGE plpgsql
    AS $$begin
-- countries
insert into callsigns_countries (callsign, country_id)
select distinct rankings.callsign, 
	(select country_id 
	 	from country_prefixes 
	 	where rankings.callsign like prefix || '%'
		order by character_length(prefix) desc 
	 	limit 1) 
from rankings left join callsigns_countries on rankings.callsign = callsigns_countries.callsign
where callsigns_countries.callsign is null;

RAISE LOG 'build_rankings: countries callsigns were assigned';
--- 9BANDS 900+---

--- country rankings---
update rankings as r set country_rank = cr._rank, country_row = cr._row
from
(select role, mode, band, rankings.callsign, country_id, _count, rank() over w as _rank, 
	row_number() over w as _row from rankings join callsigns_countries on rankings.callsign = callsigns_countries.callsign 
	window w as (partition by role, mode, band, country_id order by _count desc)
	order by _row) as cr
where r.role = cr.role and r.mode = cr.mode and r.band = cr.band and r.callsign = cr.callsign;

RAISE LOG 'build_rankings: rankings by country are ready';
end
$$;


ALTER FUNCTION public.build_rankings_countries() OWNER TO postgres;

--
-- Name: build_rankings_data(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.build_rankings_data() RETURNS void
    LANGUAGE sql
    AS $$delete from rda_activator;
lock table rda_hunter in SHARE ROW EXCLUSIVE mode;
delete from rda_hunter;

insert into rda_hunter (hunter, mode, band, rda)
select distinct callsign, mode, band, rda from qso;

insert into rda_activator (activator, rda, mode, band, callsigns)
select activator, rda, mode, band, count(distinct (callsign, dt)) as callsigns from
(select activators.activator, rda, mode, band, callsign, dt 
from qso join activators on qso.upload_id = activators.upload_id
union all
select activator, rda, mode, band, callsign, dt from qso
where upload_id is null) as qso
group by activator, rda, mode, band;

insert into rda_hunter
select activator, rda, band, mode
from rda_activator
where callsigns > 49 and not exists 
(select 1 from rda_hunter where hunter = activator and rda_hunter.rda = rda_activator.rda and rda_hunter.band = rda_activator.band and rda_hunter.mode = rda_activator.mode);

insert into rda_hunter
select activator, rda, band, null
from
(select activator, rda, band
from rda_activator
group by activator, rda, band
having sum(callsigns) > 49) as rda_activator_tm
where not exists
(select 1 from rda_hunter where hunter = activator and rda_hunter.rda = rda_activator_tm.rda and rda_hunter.band = rda_activator_tm.band);

insert into rda_hunter
select activator, rda, null, null
from
(select activator, rda
from rda_activator
group by activator, rda
having sum(callsigns) > 99) as rda_activator_tt
where not exists
(select 1 from rda_hunter where hunter = activator and rda_hunter.rda = rda_activator_tt.rda);
$$;


ALTER FUNCTION public.build_rankings_data() OWNER TO postgres;

--
-- Name: build_rankings_main(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.build_rankings_main() RETURNS void
    LANGUAGE plpgsql
    AS $$
declare 
	_9band_tr smallint;

begin
delete from rankings;

with rda_act_m_b as 
(select activator, mode, band, rda
from rda_activator
where callsigns > 49),

act_m_b as 
(select activator, mode, band, count(rda), rank() over w, row_number() over w
from rda_act_m_b
group by activator, mode, band
window w as (partition by mode, band order by count(rda) desc)),

act_t_b as
(select activator, band, count(rda), rank() over w, row_number() over w 
from
(select activator, rda, band
from rda_activator
group by activator, rda, band
having sum(callsigns) > 49) as act_total_band_f
group by activator, band
window w as (partition by band order by count(rda) desc)),

hnt_t_b as 
(select 'hunter', 'total', band, hunter, count(distinct rda), rank() over w, row_number() over w
from rda_hunter
where band is not null
group by hunter, band
window w as (partition by band order by count(distinct rda) desc))

insert into rankings

-- ACTIVATORS --

-- mode, band
select 'activator', mode, band, activator, count, rank, row_number from act_m_b 

union all

-- mode, bandsSum
select 'activator', mode, 'bandsSum', activator, sum(count), rank() over w, row_number() over w 
from act_m_b
group by activator, mode
window w as (partition by mode order by sum(count) desc)

union all

-- mode, total
select 'activator', mode, 'total', activator, count(rda), rank() over w, row_number() over w 
from
(select activator, mode, rda
from rda_activator
group by activator, mode, rda
having sum(callsigns) > 99) as act_m_total_f
group by activator, mode
window w as (partition by mode order by count(rda) desc)

union all
-- total, total
select 'activator', 'total', 'total', activator, count(rda), rank() over w, row_number() over w 
from
(select activator, rda
from rda_activator
group by activator, rda
having sum(callsigns) > 99) as act_total_total_f
group by activator
window w as (order by count(rda) desc)

union all
-- total, bandsSum
select 'activator', 'total', 'bandsSum', activator, sum(count), rank() over w, row_number() over w 
from act_t_b
group by activator
window w as (order by sum(count) desc)

union all
--total, band
select 'activator', 'total', band, activator, count, rank, row_number
from act_t_b

--- HUNTERS ---

union all
--mode, band
select 'hunter', mode, band, hunter, count(*), rank() over w, row_number() over w 
from rda_hunter
where mode is not null and band is not null
group by hunter, mode, band
window w as (partition by mode, band order by count(*) desc)

union all
--mode, bandsSum
select 'hunter', mode, 'bandsSum', hunter, count(*), rank() over w, row_number() over w 
from rda_hunter
where mode is not null
group by hunter, mode
window w as (partition by mode order by count(*) desc)

union all
--mode, total
select 'hunter', mode, 'total', hunter, count(distinct rda), rank() over w, row_number() over w 
from rda_hunter
where mode is not null
group by hunter, mode
window w as (partition by mode order by count(distinct rda) desc)

union all
--total, total
select 'hunter', 'total', 'total', hunter, count(distinct rda), rank() over w, row_number() over w 
from rda_hunter
where band is not null
group by hunter
window w as (order by count(distinct rda) desc)

union all
--total, band
select 'hunter', 'total', band, hunter, count, rank, row_number
from hnt_t_b

union all
--total, bandsSum 
select 'hunter', 'total', 'bandsSum', hunter, sum(count), rank() over w, row_number() over w
from hnt_t_b
group by hunter
window w as (order by sum(count) desc)

--- 9BANDS ---

union all

select 'hunter', 'total', '9BAND', hunter, sum(points), rank() over w, row_number() over w from
(select hunter, band, least(100, count(distinct rda)) as points
from rda_hunter
where band is not null
group by hunter, band) as s
group by hunter
window w as (order by sum(points) desc)

--- 9BANDS EXTREME---

union all

select 'hunter', 'total', '9BAND-X', hunter, count(*), rank() over w, row_number() over w 
from (select hunter, rda
from rda_hunter
where band is not null
group by hunter, rda
having count(distinct band) = 9) as s0
group by hunter
window w as (order by count(*) desc);

RAISE LOG 'build_rankings: main rankings are ready';

_9band_tr = 100;

while exists (select callsign from rankings where role = 'hunter' and mode = 'total' and band = '9BAND' and _count = 9*_9band_tr)
  loop
   update rankings set _count = new_count, _rank = new_rank, _row = new_row
   from
    (select hunter, sum(points) as new_count, rank() over w as new_rank, row_number() over w as new_row 
    from
      (select hunter, band, least(_9band_tr + 100, count(distinct rda)) as points
      from rda_hunter
      where band is not null and hunter in (select callsign from rankings where role = 'hunter' and mode = 'total' and band = '9BAND' and _count = 9*_9band_tr)
      group by hunter, band) as s
    group by hunter
    window w as (order by sum(points) desc)) as p2
   where callsign = hunter and role = 'hunter' and mode = 'total' and band = '9BAND';
  _9band_tr = _9band_tr + 100;
end loop;

RAISE LOG 'build_rankings: 9bands loop is finished';
end
$$;


ALTER FUNCTION public.build_rankings_main() OWNER TO postgres;

--
-- Name: build_rankings_purge_rda(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.build_rankings_purge_rda() RETURNS void
    LANGUAGE plpgsql
    AS $$
begin
RAISE LOG 'build_rankings: rda tables purge start';
-- rda

delete from rda_activator;
delete from rda_hunter 
where 1 not in (select 1 from qso left join uploads
		on qso.upload_id = uploads.id
        where qso.callsign = hunter and qso.mode = rda_hunter.mode and 
            qso.band = rda_hunter.band and qso.rda = rda_hunter.rda and 
			(qso.upload_id is null or uploads.enabled));
RAISE LOG 'build_rankings: rda tables were purged';
end
$$;


ALTER FUNCTION public.build_rankings_purge_rda() OWNER TO postgres;

--
-- Name: check_qso(character varying, character varying, character, character, character, timestamp without time zone); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying) RETURNS record
    LANGUAGE plpgsql
    AS $$
declare 
  str_callsign character varying(32);
  str_station_callsign character varying(32);
  blacklist_begin date;
  blacklist_end date;
begin
  str_callsign = strip_callsign(_callsign);
  str_station_callsign = strip_callsign(_station_callsign);
  if str_callsign is null or str_station_callsign is null or str_callsign = str_station_callsign
  then
    raise 'cfmrda_db_error:Позывной некорректен или совпадает с позывным корреспондента';
  end if;
  if (_ts < '06-12-1991') 
  then
    raise 'cfmrda_db_error:Связь проведена до начала программы RDA (06-12-1991)';
  end if;
  if (_band = '10' and _mode = 'SSB')
  then
    raise 'cfmrda_db_error:Мода SSB некорректна на диапазоне 10MHz';
  end if;
  select date_begin, date_end  into blacklist_begin, blacklist_end
  	from stations_blacklist
	where _station_callsign = stations_blacklist.callsign and
		(date_begin is null or _ts >= stations_blacklist.date_begin) and 
		(date_end is null or _ts >= stations_blacklist.date_end);
  if found
  then
	raise 'cfmrda_db_error:Станция в черном списке: % с % по %', _station_callsign, coalesce(blacklist_begin::text, '-'), coalesce(blacklist_end::text, '-');    
  end if;
  /*check and replace obsolete callsign */
  select old_callsigns.new into new_callsign
    from old_callsigns 
    where old_callsigns.old = str_callsign and confirmed;
  if not found
  then  
    new_callsign = str_callsign;
  end if;
  /*check and replace obsolete rda*/
  select old_rda.new into new_rda
    from old_rda 
    where old_rda.old = _rda and 
	(dt_start is null or dt_start < _ts) and
	(dt_stop is null or dt_stop > _ts);
  if not found
  then  
    new_rda = _rda;
  elsif new_rda is null
  then
    raise 'cfmrda_db_error:Некорректный район RDA (%)', _rda;    
  end if;  
  if not exists (select from rda where rda = new_rda)
  then
    raise 'cfmrda_db_error:Некорректный район RDA (%)', _rda;    
  end if;    
  if exists (select from qso where qso.callsign = new_callsign and qso.station_callsign = _station_callsign 
    and qso.rda = new_rda and qso.mode = _mode and qso.band = _band and qso.tstamp::date = _ts::date)
  then
      raise exception using
            errcode='CR001',
            message='cfmrda_db_error:Связь уже внесена в базу данных';
  end if;
 end
$$;


ALTER FUNCTION public.check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying) OWNER TO postgres;

--
-- Name: hunters_rdas(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.hunters_rdas() RETURNS TABLE(callsign character varying, rda character)
    LANGUAGE plpgsql
    AS $$
declare 
  hunter varchar(32);
begin
  for hunter in 
    WITH RECURSIVE t AS (
            (select qso.callsign from qso order by qso.callsign limit 1)
            union all
            select (select qso.callsign from qso where qso.callsign > t.callsign
                order by qso.callsign limit 1)
            from t where t.callsign is not null)
        select * from t where t.callsign is not null
  loop
    return query WITH RECURSIVE t AS (
            (select qso.rda from qso where qso.callsign = hunter order by qso.rda limit 1)
            union all
            select (select qso.rda from qso where qso.rda > t.rda and qso.callsign = hunter
                order by qso.rda limit 1)
            from t where t.rda is not null)
        select hunter, t.rda from t where t.rda is not null;
  end loop;
end
$$;


ALTER FUNCTION public.hunters_rdas() OWNER TO postgres;

--
-- Name: rankings_json(character varying); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.rankings_json(condition character varying) RETURNS json
    LANGUAGE plpgsql
    AS $$declare 
  data json;
begin
  execute 'select json_object_agg(role, data) as data from ' 
	|| '(select role, json_object_agg(mode, data) as data from '
	|| '(select role, mode, json_object_agg(band, data) as data from '
	|| '(select role, mode, band, json_agg(json_build_object(''callsign'', callsign, '
	|| '''count'', _count, ''rank'', _rank, ''row'', _row) order by _row) as data from '
	|| '(select * from rankings where ' || condition || ') as l_0 '
	|| 'group by role, mode, band) as l_1 '
	|| 'group by role, mode) as l_2 '
	|| 'group by role) as l_3'
  into data;
  return data;
end$$;


ALTER FUNCTION public.rankings_json(condition character varying) OWNER TO postgres;

--
-- Name: rankings_json(character varying, character varying, character varying, integer, integer, character varying); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.rankings_json(_role character varying, _mode character varying, _band character varying, _row_from integer, _row_to integer, _callsign character varying) RETURNS json
    LANGUAGE plpgsql
    AS $$declare 
begin
  return (select json_object_agg(role, data) as data from 
	(select role, json_object_agg(mode, data) as data from 
		(select role, mode, json_object_agg(band, data) as data from 
			(select role, mode, band, json_agg(json_build_object('callsign', callsign, 
				'count', _count, 'rank', _rank, 'row', _row) order by _row) as data from 
					(select * from rankings 
					 where (role = _role or _role is null) and 
					 	(mode = _mode or _mode is null) and
            			(band = _band or _band is null) and 
					 	(_row >= _row_from or _row_from is null) and 
					 	(_row <= _row_to or _row_to is null) and 
					 	(callsign = _callsign or _callsign is null)
					) as l_0 
			group by role, mode, band) as l_1 
		group by role, mode) as l_2 
	group by role) as l_3);
end$$;


ALTER FUNCTION public.rankings_json(_role character varying, _mode character varying, _band character varying, _row_from integer, _row_to integer, _callsign character varying) OWNER TO postgres;

--
-- Name: rankings_json(character varying, character varying, character varying, integer, integer, character varying, integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.rankings_json(_role character varying, _mode character varying, _band character varying, _row_from integer, _row_to integer, _callsign character varying, _country_id integer) RETURNS json
    LANGUAGE plpgsql
    AS $$declare 
begin
  return (select json_object_agg(role, data) as data from 
	(select role, json_object_agg(mode, data) as data from 
		(select role, mode, json_object_agg(band, data) as data from 
			(select role, mode, band, json_agg(json_build_object('callsign', callsign, 
				'count', _count, 'rank', _rank, 'row', _row) order by _row) as data from 
					(select role, mode, band, r.callsign, _count, 
					 	case when _country_id is null then _rank
					 		else country_rank 
					 	end as _rank,
					 	case when _country_id is null then _row
					 		else country_row
					 	end as _row
					 from rankings as r join callsigns_countries as cc on r.callsign = cc.callsign
					 where (role = _role or _role is null) and 
					 	(mode = _mode or _mode is null) and
            			(band = _band or _band is null) and 
					 	(_row_from is null or (
							(_country_id is null and _row >= _row_from) or
							(_country_id is not null and country_row >= _row_from)
						)) and 
					 	(_row_to is null or (
							(_country_id is null and _row <= _row_to) or
							(_country_id is not null and country_row <= _row_to)
						)) and 
					 	(r.callsign = _callsign or _callsign is null) and
					    (country_id = _country_id or _country_id is null)
					) as l_0 
			group by role, mode, band) as l_1 
		group by role, mode) as l_2 
	group by role) as l_3);
end$$;


ALTER FUNCTION public.rankings_json(_role character varying, _mode character varying, _band character varying, _row_from integer, _row_to integer, _callsign character varying, _country_id integer) OWNER TO postgres;

--
-- Name: rankings_json_country(character varying, character varying, character varying, integer, integer, character varying, integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.rankings_json_country(_role character varying, _mode character varying, _band character varying, _row_from integer, _row_to integer, _callsign character varying, _country_id integer) RETURNS json
    LANGUAGE plpgsql
    AS $$declare 
begin
  return (select json_object_agg(role, data) as data from 
	(select role, json_object_agg(mode, data) as data from 
		(select role, mode, json_object_agg(band, data) as data from 
			(select role, mode, band, json_agg(json_build_object('callsign', callsign, 
				'count', _count, 'rank', _rank, 'row', _row) order by _row) as data from 
					(select * from
						(select role, mode, band, callsign, _count, rank() over w as _rank, 
						 	row_number() over w as _row from rankings 
							where (role = _role or _role is null) and 
					 			(mode = _mode or _mode is null) and
            					(band = _band or _band is null) and 
								callsign in 
									(select callsign 
									 	from callsigns_countries 
									 	where country_id = _country_id)
							window w as (partition by role, mode, band order by _count desc)
							order by _row) as country_rankings
					 where (callsign = _callsign or _callsign is null) and
						(_row >= _row_from or _row_from is null) and 
						(_row <= _row_to or _row_to is null) 				 
					) as l_0 
			group by role, mode, band) as l_1 
		group by role, mode) as l_2 
	group by role) as l_3);
end$$;


ALTER FUNCTION public.rankings_json_country(_role character varying, _mode character varying, _band character varying, _row_from integer, _row_to integer, _callsign character varying, _country_id integer) OWNER TO postgres;

--
-- Name: strip_callsign(character varying); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.strip_callsign(callsign character varying) RETURNS character varying
    LANGUAGE plpgsql IMMUTABLE
    AS $$begin
  if substring(callsign from '[^\dA-Z/]') is not null then
    return null;
  end if;
  return substring(callsign from '[\d]*[A-Z]+\d+[A-Z]+');
end$$;


ALTER FUNCTION public.strip_callsign(callsign character varying) OWNER TO postgres;

--
-- Name: tf_activators_bi(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.tf_activators_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  new.activator = strip_callsign(new.activator);
  if exists (select from old_callsigns where confirmed and old_callsigns.old = new.activator)
  then
    select old_callsigns.new into new.activator from old_callsigns where confirmed and old_callsigns.old = new.activator;
  end if;
  if new.activator is null
  then
    return null;
  elsif exists (select 1 from activators where upload_id = new.upload_id and activator = new.activator)
  then
    return null;
  else
    return new;
  end if;
 end$$;


ALTER FUNCTION public.tf_activators_bi() OWNER TO postgres;

--
-- Name: tf_callsigns_rda_bi(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.tf_callsigns_rda_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
  if exists (select from callsigns_rda 
    where callsign = new.callsign and source = new.source and 
      rda = new.rda and
      (dt_start is null or dt_start <= new.dt_start) and
      (dt_stop is null or dt_stop >= new.dt_stop))
  then
    update callsigns_rda
      set ts = now()
      where callsign = new.callsign and source = new.source and 
        rda = new.rda and
        (dt_start is null or dt_start <= new.dt_start) and
        (dt_stop is null or dt_stop >= new.dt_stop);
    return null;
  end if;  
  /*check and replace obsolete rda*/
  if exists (select from old_rda where old_rda.old = new.rda and old_rda.new is not null 
	and dt_start is null and dt_stop is null)
  then  
    select old_rda.new from old_rda where old_rda.old = new.rda
      into new.rda;
  end if;  
  if (new.rda <> '***') and not exists (select from rda where rda = new.rda)
  then  
    raise 'cfmrda_db_error:Некорректный район RDA (%)', new.rda;    
  end if;     
  if (new.source = 'QRZ.ru')
  then
    update callsigns_rda 
      set dt_stop = now() 
      where callsign = new.callsign and source = 'QRZ.ru' and dt_stop is null;
  end if;
  return new;
end$$;


ALTER FUNCTION public.tf_callsigns_rda_bi() OWNER TO postgres;

--
-- Name: tf_cfm_qsl_qso_bi(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.tf_cfm_qsl_qso_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$declare 
  new_rda character varying(5);
begin
  /*check and replace obsolete rda*/
  select old_rda.new into new_rda
    from old_rda 
    where old_rda.old = new.rda and 
	(dt_start < new.tstamp or dt_start is null) and
	(dt_stop > new.tstamp or dt_stop is null);
  if not found
  then  
    new_rda = new.rda;
  elsif new_rda is null
  then
    raise 'cfmrda_db_error:Некорректный район RDA (%)', new.rda;    
  end if;  
  if not exists (select from rda where rda = new_rda)
  then
    raise 'cfmrda_db_error:Некорректный район RDA (%)', new.rda;    
  end if;    
  if exists (select from qso where qso.callsign = strip_callsign(new.callsign) and qso.rda = new_rda and qso.band = new.band and qso.mode = new.mode) then
    raise 'cfmrda_db_error:Этот RDA у вас уже подтвержден ⇒ <b>(%, %, %)</b> ⇐ This RDA is already confirmed for you.', new.rda, new.mode, new.band || 'MHz';
  end if;
  if (now() - new.tstamp < interval '10 days')
  then
    raise 'cfmrda_db_error:На проверку принимаются карточки с датой не менее 10 дней до текущей. Only cards with a date at least 10 days before today are accepted.';
  end if;
  perform check_qso(new.callsign, new.station_callsign, new_rda, new.band, new.mode, new.tstamp);
/*  if exists (select 1 from cfm_qsl_qso
	where callsign = new.callsign and rda = new.rda
	and station_callsign = new.station_callsign
	and band = new.band and mode = new.mode) then
    return null;
   end if;   */
   return new;
 end
$$;


ALTER FUNCTION public.tf_cfm_qsl_qso_bi() OWNER TO postgres;

--
-- Name: tf_cfm_qsl_qso_bu(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.tf_cfm_qsl_qso_bu() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  if new.state and (not old.state or old.state is null) then
    perform check_qso(new.callsign, new.station_callsign, new.rda, new.band, new.mode, new.tstamp);
    insert into qso (callsign, station_callsign, rda, band, mode, tstamp)
      values (coalesce(new.new_callsign, new.callsign), new.station_callsign, new.rda,
        new.band, new.mode, new.tstamp);
    new.status_date = now();
  end if;
  return new;
exception
  when sqlstate 'CR001' then
     return new;
end;
  
   $$;


ALTER FUNCTION public.tf_cfm_qsl_qso_bu() OWNER TO postgres;

--
-- Name: tf_cfm_request_qso_bi(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.tf_cfm_request_qso_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  perform check_qso(new.callsign, new.station_callsign, new.rda, new.band, new.mode, new.tstamp);
  return new;
 end$$;


ALTER FUNCTION public.tf_cfm_request_qso_bi() OWNER TO postgres;

--
-- Name: tf_old_callsigns_aiu(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.tf_old_callsigns_aiu() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  if new.confirmed then
    update qso 
      set callsign = new.new, old_callsign = new.old 
      where callsign = new.old;
    update activators as a1
      set activator = new.new
      where activator = new.old and not exists 
        (select from activators as a2 
        where a2.activator = new.new and a2.upload_id = a1.upload_id);
    delete from activators 
      where activator = new.old;
    insert into rda_hunter (hunter, rda, band, mode)
      select new.new, rda, band, mode
        from rda_hunter where hunter = new.old
        on conflict on constraint rda_hunter_uq do nothing;
    delete from rda_hunter
      where hunter = new.old;
  end if;
  return new;
end$$;


ALTER FUNCTION public.tf_old_callsigns_aiu() OWNER TO postgres;

--
-- Name: tf_qso_ai(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.tf_qso_ai() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
  insert into rda_hunter values (new.callsign, new.rda, new.band, new.mode)
  on conflict on constraint rda_hunter_uq do nothing;
  return new;
 end$$;


ALTER FUNCTION public.tf_qso_ai() OWNER TO postgres;

--
-- Name: tf_qso_au(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.tf_qso_au() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  if old.rda <> new.rda then
      insert into rda_hunter values (new.callsign, new.rda, new.band, new.mode)
      on conflict on constraint rda_hunter_uq do nothing;
  end if;
  return new;
end$$;


ALTER FUNCTION public.tf_qso_au() OWNER TO postgres;

--
-- Name: tf_qso_bi(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.tf_qso_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
declare 
  new_callsign character varying(32);
begin
  new.callsign = strip_callsign(new.callsign);
  select * from check_qso(new.callsign, new.station_callsign, new.rda, new.band, new.mode, new.tstamp)
    into new_callsign, new.rda;
  if new_callsign <> new.callsign
  then
    new.old_callsign = new.callsign;
    new.callsign = new_callsign;
  end if;
  new.dt = date(new.tstamp);
  if new.upload_id is null or not exists (select upload_id from activators where activators.upload_id = new.upload_id)
  then
    new.activator = strip_callsign(new.station_callsign);
  end if;
  return new;
 end
$$;


ALTER FUNCTION public.tf_qso_bi() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activators; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.activators (
    upload_id bigint NOT NULL,
    activator character varying(32) NOT NULL
);


ALTER TABLE public.activators OWNER TO postgres;

--
-- Name: activators_rating; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.activators_rating (
    activator character varying(32) NOT NULL,
    qso_year smallint NOT NULL,
    rating integer NOT NULL
);


ALTER TABLE public.activators_rating OWNER TO postgres;

--
-- Name: activators_rating_detail; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.activators_rating_detail (
    activator character varying(32) NOT NULL,
    qso_year smallint NOT NULL,
    rda character(5) NOT NULL,
    points integer NOT NULL,
    mult smallint NOT NULL
);


ALTER TABLE public.activators_rating_detail OWNER TO postgres;

--
-- Name: active_locks; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.active_locks AS
 SELECT t.schemaname,
    t.relname,
    l.locktype,
    l.page,
    l.virtualtransaction,
    l.pid,
    l.mode,
    l.granted
   FROM (pg_locks l
     JOIN pg_stat_all_tables t ON ((l.relation = t.relid)))
  WHERE ((t.schemaname <> 'pg_toast'::name) AND (t.schemaname <> 'pg_catalog'::name))
  ORDER BY t.schemaname, t.relname;


ALTER TABLE public.active_locks OWNER TO postgres;

--
-- Name: callsigns_countries; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.callsigns_countries (
    callsign character varying(64) NOT NULL,
    country_id smallint
);


ALTER TABLE public.callsigns_countries OWNER TO postgres;

--
-- Name: callsigns_meta; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.callsigns_meta (
    callsign character varying(64) NOT NULL,
    disable_autocfm boolean,
    comments character varying(512)
);


ALTER TABLE public.callsigns_meta OWNER TO postgres;

--
-- Name: callsigns_rda; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.callsigns_rda (
    callsign character varying(64) NOT NULL,
    dt_start date,
    dt_stop date,
    source character varying(64),
    ts timestamp without time zone DEFAULT now() NOT NULL,
    rda character(5) NOT NULL,
    id integer NOT NULL,
    comment character varying(256)
);


ALTER TABLE public.callsigns_rda OWNER TO postgres;

--
-- Name: callsigns_rda_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.callsigns_rda_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.callsigns_rda_id_seq OWNER TO postgres;

--
-- Name: callsigns_rda_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.callsigns_rda_id_seq OWNED BY public.callsigns_rda.id;


--
-- Name: cfm_qsl; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cfm_qsl (
    id integer NOT NULL,
    user_cs character varying(32) NOT NULL,
    image character varying(128),
    image_back character varying(128),
    comment character varying(512)
);


ALTER TABLE public.cfm_qsl OWNER TO postgres;

--
-- Name: cfm_qsl_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cfm_qsl_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.cfm_qsl_id_seq OWNER TO postgres;

--
-- Name: cfm_qsl_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cfm_qsl_id_seq OWNED BY public.cfm_qsl.id;


--
-- Name: cfm_qsl_qso; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cfm_qsl_qso (
    id integer NOT NULL,
    station_callsign character varying(32),
    rda character(5) NOT NULL,
    band character varying(16) NOT NULL,
    mode character varying(16) NOT NULL,
    callsign character varying(32) NOT NULL,
    new_callsign character varying(32),
    tstamp timestamp without time zone NOT NULL,
    state boolean,
    comment character varying(256),
    status_date timestamp without time zone,
    admin character varying(64),
    qsl_id integer NOT NULL
);


ALTER TABLE public.cfm_qsl_qso OWNER TO postgres;

--
-- Name: cfm_qsl_qso_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cfm_qsl_qso_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.cfm_qsl_qso_id_seq OWNER TO postgres;

--
-- Name: cfm_qsl_qso_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cfm_qsl_qso_id_seq OWNED BY public.cfm_qsl_qso.id;


--
-- Name: cfm_request_blacklist; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cfm_request_blacklist (
    callsign character varying(32) NOT NULL
);


ALTER TABLE public.cfm_request_blacklist OWNER TO postgres;

--
-- Name: cfm_request_qso; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cfm_request_qso (
    id integer NOT NULL,
    correspondent character varying(32) NOT NULL,
    callsign character varying(32) NOT NULL,
    station_callsign character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(8) NOT NULL,
    mode character varying(16) NOT NULL,
    tstamp timestamp without time zone NOT NULL,
    hunter_email character varying(64),
    rec_rst character varying(8) NOT NULL,
    sent_rst character varying(8) NOT NULL,
    sent boolean DEFAULT false NOT NULL,
    correspondent_email character varying(64) NOT NULL,
    req_tstamp timestamp without time zone DEFAULT now(),
    status_tstamp timestamp without time zone DEFAULT now(),
    viewed boolean DEFAULT false,
    comment character varying(256),
    state boolean,
    user_cs character varying(32)
);


ALTER TABLE public.cfm_request_qso OWNER TO postgres;

--
-- Name: cfm_request_qso_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cfm_request_qso_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.cfm_request_qso_id_seq OWNER TO postgres;

--
-- Name: cfm_request_qso_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cfm_request_qso_id_seq OWNED BY public.cfm_request_qso.id;


--
-- Name: cfm_requests; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cfm_requests (
    callsign character varying(32) NOT NULL,
    tstamp timestamp without time zone
);


ALTER TABLE public.cfm_requests OWNER TO postgres;

--
-- Name: countries_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.countries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.countries_id_seq OWNER TO postgres;

--
-- Name: countries; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.countries (
    id smallint DEFAULT nextval('public.countries_id_seq'::regclass) NOT NULL,
    name character varying(64) NOT NULL
);


ALTER TABLE public.countries OWNER TO postgres;

--
-- Name: country_prefixes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.country_prefixes (
    prefix character varying(8) NOT NULL,
    country_id smallint NOT NULL
);


ALTER TABLE public.country_prefixes OWNER TO postgres;

--
-- Name: ext_loggers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ext_loggers (
    callsign character varying(32) NOT NULL,
    logger character varying(8) NOT NULL,
    login_data json,
    state integer,
    qso_count integer,
    last_updated date,
    id integer NOT NULL
);


ALTER TABLE public.ext_loggers OWNER TO postgres;

--
-- Name: ext_loggers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ext_loggers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.ext_loggers_id_seq OWNER TO postgres;

--
-- Name: ext_loggers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ext_loggers_id_seq OWNED BY public.ext_loggers.id;


--
-- Name: old_callsigns; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.old_callsigns (
    old character varying(32) NOT NULL,
    new character varying(32) NOT NULL,
    confirmed boolean
);


ALTER TABLE public.old_callsigns OWNER TO postgres;

--
-- Name: old_rda; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.old_rda (
    old character varying(5) NOT NULL,
    new character varying(5),
    dt_start date,
    dt_stop date
);


ALTER TABLE public.old_rda OWNER TO postgres;

--
-- Name: qso; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.qso (
    id integer NOT NULL,
    upload_id integer,
    callsign character varying(32) NOT NULL,
    station_callsign character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(8) NOT NULL,
    mode character varying(16) NOT NULL,
    tstamp timestamp without time zone NOT NULL,
    dt date DEFAULT date(now()) NOT NULL,
    old_callsign character varying(32),
    rec_ts timestamp without time zone DEFAULT now(),
    activator character varying(32)
);
ALTER TABLE ONLY public.qso ALTER COLUMN upload_id SET STATISTICS 10000;


ALTER TABLE public.qso OWNER TO postgres;

--
-- Name: qso_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.qso_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.qso_id_seq OWNER TO postgres;

--
-- Name: qso_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.qso_id_seq OWNED BY public.qso.id;


--
-- Name: ra_t; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ra_t (
    activator character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(8) NOT NULL,
    mode character varying(16) NOT NULL,
    callsigns bigint
);


ALTER TABLE public.ra_t OWNER TO postgres;

--
-- Name: rankings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rankings (
    role character varying(16) NOT NULL,
    mode character varying(16) NOT NULL,
    band character varying(8) NOT NULL,
    callsign character varying(32) NOT NULL,
    _count integer,
    _rank integer,
    _row integer,
    country_rank integer,
    country_row integer
);


ALTER TABLE public.rankings OWNER TO postgres;

--
-- Name: rda; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rda (
    rda character(5) NOT NULL
);


ALTER TABLE public.rda OWNER TO postgres;

--
-- Name: rda_activator; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rda_activator (
    activator character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(8) NOT NULL,
    mode character varying(16) NOT NULL,
    callsigns bigint
);


ALTER TABLE public.rda_activator OWNER TO postgres;

--
-- Name: rda_hunter; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rda_hunter (
    hunter character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(16),
    mode character varying(16)
);


ALTER TABLE public.rda_hunter OWNER TO postgres;

--
-- Name: stat_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.stat_log (
    tstamp timestamp without time zone DEFAULT now() NOT NULL,
    msg character varying(512) NOT NULL
);


ALTER TABLE public.stat_log OWNER TO postgres;

--
-- Name: stations_blacklist; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.stations_blacklist (
    callsign character varying(64) NOT NULL,
    date_begin date,
    date_end date
);


ALTER TABLE public.stations_blacklist OWNER TO postgres;

--
-- Name: uploads; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.uploads (
    id integer NOT NULL,
    user_cs character varying(32) NOT NULL,
    tstamp timestamp without time zone DEFAULT now() NOT NULL,
    date_start date NOT NULL,
    date_end date NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    hash character varying(64) DEFAULT ''::character varying NOT NULL,
    upload_type character varying(32) DEFAULT 'adif'::character varying,
    ext_logger_id integer
);


ALTER TABLE public.uploads OWNER TO postgres;

--
-- Name: uploads_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.uploads_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.uploads_id_seq OWNER TO postgres;

--
-- Name: uploads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.uploads_id_seq OWNED BY public.uploads.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    callsign character varying(32) NOT NULL,
    password character varying(32) NOT NULL,
    email character varying(64) NOT NULL,
    email_confirmed boolean DEFAULT false NOT NULL,
    defs jsonb
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: callsigns_rda id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.callsigns_rda ALTER COLUMN id SET DEFAULT nextval('public.callsigns_rda_id_seq'::regclass);


--
-- Name: cfm_qsl id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cfm_qsl ALTER COLUMN id SET DEFAULT nextval('public.cfm_qsl_id_seq'::regclass);


--
-- Name: cfm_qsl_qso id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cfm_qsl_qso ALTER COLUMN id SET DEFAULT nextval('public.cfm_qsl_qso_id_seq'::regclass);


--
-- Name: cfm_request_qso id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cfm_request_qso ALTER COLUMN id SET DEFAULT nextval('public.cfm_request_qso_id_seq'::regclass);


--
-- Name: ext_loggers id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ext_loggers ALTER COLUMN id SET DEFAULT nextval('public.ext_loggers_id_seq'::regclass);


--
-- Name: qso id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.qso ALTER COLUMN id SET DEFAULT nextval('public.qso_id_seq'::regclass);


--
-- Name: uploads id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.uploads ALTER COLUMN id SET DEFAULT nextval('public.uploads_id_seq'::regclass);


--
-- Name: activators activators_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activators
    ADD CONSTRAINT activators_pkey PRIMARY KEY (upload_id, activator);


--
-- Name: activators_rating_detail activators_rating_detail_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activators_rating_detail
    ADD CONSTRAINT activators_rating_detail_pkey PRIMARY KEY (activator, qso_year, rda);


--
-- Name: activators_rating activators_rating_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activators_rating
    ADD CONSTRAINT activators_rating_pkey PRIMARY KEY (activator, qso_year);


--
-- Name: callsigns_countries callsigns_country_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.callsigns_countries
    ADD CONSTRAINT callsigns_country_pkey PRIMARY KEY (callsign);


--
-- Name: callsigns_meta callsigns_meta_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.callsigns_meta
    ADD CONSTRAINT callsigns_meta_pkey PRIMARY KEY (callsign);


--
-- Name: callsigns_rda callsigns_rda_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.callsigns_rda
    ADD CONSTRAINT callsigns_rda_pkey PRIMARY KEY (id);


--
-- Name: cfm_qsl cfm_qsl_pk; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cfm_qsl
    ADD CONSTRAINT cfm_qsl_pk PRIMARY KEY (id);


--
-- Name: cfm_qsl_qso cfm_qsl_qso_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cfm_qsl_qso
    ADD CONSTRAINT cfm_qsl_qso_pkey PRIMARY KEY (id);


--
-- Name: cfm_request_blacklist cfm_request_blacklist_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cfm_request_blacklist
    ADD CONSTRAINT cfm_request_blacklist_pkey PRIMARY KEY (callsign);


--
-- Name: cfm_request_qso cfm_request_qso_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cfm_request_qso
    ADD CONSTRAINT cfm_request_qso_pkey PRIMARY KEY (id);


--
-- Name: countries countries_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.countries
    ADD CONSTRAINT countries_name_key UNIQUE (name);


--
-- Name: countries countries_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.countries
    ADD CONSTRAINT countries_pkey PRIMARY KEY (id);


--
-- Name: country_prefixes country_prefixes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.country_prefixes
    ADD CONSTRAINT country_prefixes_pkey PRIMARY KEY (prefix);


--
-- Name: ext_loggers ext_loggers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ext_loggers
    ADD CONSTRAINT ext_loggers_pkey PRIMARY KEY (id);


--
-- Name: old_callsigns old_callsigns_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.old_callsigns
    ADD CONSTRAINT old_callsigns_pkey PRIMARY KEY (old, new);


--
-- Name: old_rda old_rda_old_dt_start_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.old_rda
    ADD CONSTRAINT old_rda_old_dt_start_key UNIQUE (old, dt_start);


--
-- Name: qso qso_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.qso
    ADD CONSTRAINT qso_pkey PRIMARY KEY (id);


--
-- Name: cfm_requests qso_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cfm_requests
    ADD CONSTRAINT qso_requests_pkey PRIMARY KEY (callsign);


--
-- Name: ra_t ra_t_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ra_t
    ADD CONSTRAINT ra_t_pkey PRIMARY KEY (activator, rda, band, mode);


--
-- Name: rankings rankings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rankings
    ADD CONSTRAINT rankings_pkey PRIMARY KEY (role, mode, band, callsign);


--
-- Name: rda_activator rda_activator_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rda_activator
    ADD CONSTRAINT rda_activator_pkey PRIMARY KEY (activator, rda, band, mode);


--
-- Name: rda_hunter rda_hunter_uq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rda_hunter
    ADD CONSTRAINT rda_hunter_uq UNIQUE (hunter, rda, band, mode);


--
-- Name: rda rda_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rda
    ADD CONSTRAINT rda_pkey PRIMARY KEY (rda);


--
-- Name: stat_log stat_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stat_log
    ADD CONSTRAINT stat_log_pkey PRIMARY KEY (tstamp, msg);


--
-- Name: stations_blacklist stations_blacklist_callsign_date_begin_date_end_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stations_blacklist
    ADD CONSTRAINT stations_blacklist_callsign_date_begin_date_end_key UNIQUE (callsign, date_begin, date_end);


--
-- Name: uploads uploads_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.uploads
    ADD CONSTRAINT uploads_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (callsign);


--
-- Name: activators_activator_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX activators_activator_idx ON public.activators USING btree (activator);


--
-- Name: callsigns_rda_callsign_dt_start_dt_stop_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX callsigns_rda_callsign_dt_start_dt_stop_idx ON public.callsigns_rda USING btree (callsign, dt_start, dt_stop);


--
-- Name: cfm_request_qso_correspondent_callsign_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX cfm_request_qso_correspondent_callsign_idx ON public.cfm_request_qso USING btree (correspondent);


--
-- Name: cfm_request_qso_sent_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX cfm_request_qso_sent_idx ON public.cfm_request_qso USING btree (sent);


--
-- Name: cfm_request_qso_user_cs_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX cfm_request_qso_user_cs_idx ON public.cfm_request_qso USING btree (user_cs);


--
-- Name: fki_qso_rda_fkey; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX fki_qso_rda_fkey ON public.qso USING btree (rda);


--
-- Name: idx_pfx_length; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_pfx_length ON public.country_prefixes USING btree (character_length((prefix)::text) DESC);


--
-- Name: old_callsigns_confirmed_new_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX old_callsigns_confirmed_new_idx ON public.old_callsigns USING btree (confirmed, new);


--
-- Name: old_callsigns_confirmed_old_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX old_callsigns_confirmed_old_idx ON public.old_callsigns USING btree (confirmed, old);


--
-- Name: old_callsigns_uq; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX old_callsigns_uq ON public.old_callsigns USING btree (old) WHERE confirmed;


--
-- Name: qso_act_mode_band_rda_callsign_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX qso_act_mode_band_rda_callsign_idx ON public.qso USING btree (activator, mode, band, rda, callsign, dt) WHERE (activator IS NOT NULL);


--
-- Name: qso_callsign_mode_band_rda_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX qso_callsign_mode_band_rda_idx ON public.qso USING btree (callsign, mode, band, rda);


--
-- Name: qso_expedition_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX qso_expedition_idx ON public.qso USING btree (upload_id, activator, rda, band, callsign, date_part('year'::text, dt)) WHERE (((station_callsign)::text ~~ '%/M'::text) OR ((station_callsign)::text ~~ '%/P'::text));


--
-- Name: qso_upload_id_mode_band_rda_callsign_dt_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX qso_upload_id_mode_band_rda_callsign_dt_idx ON public.qso USING btree (upload_id, mode, band, rda, callsign, dt);


--
-- Name: ra_t_activator_rda_band_mode_callsigns_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ra_t_activator_rda_band_mode_callsigns_idx ON public.ra_t USING btree (activator, rda, band, mode, callsigns);


--
-- Name: rankings_callsign_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX rankings_callsign_idx ON public.rankings USING btree (callsign);


--
-- Name: rankings_top100; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX rankings_top100 ON public.rankings USING btree (role, mode, band, callsign, _count, _rank) WHERE (_rank < 101);


--
-- Name: rda_activator_activator_rda_band_mode_callsigns_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX rda_activator_activator_rda_band_mode_callsigns_idx ON public.rda_activator USING btree (activator, rda, band, mode, callsigns);


--
-- Name: rda_hunter_callsign_rda_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX rda_hunter_callsign_rda_idx ON public.rda_hunter USING btree (hunter, rda);


--
-- Name: rda_hunter_hunter_mode_band_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX rda_hunter_hunter_mode_band_idx ON public.rda_hunter USING btree (hunter, mode, band);


--
-- Name: unique_callsigns_rda_qrz; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX unique_callsigns_rda_qrz ON public.callsigns_rda USING btree (callsign) WHERE ((source)::text = 'QRZ.ru'::text);


--
-- Name: uploads_id_enabled_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX uploads_id_enabled_idx ON public.uploads USING btree (id, enabled);


--
-- Name: uploads_id_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX uploads_id_idx ON public.uploads USING btree (id);


--
-- Name: uploads_id_user_cs_upload_type_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX uploads_id_user_cs_upload_type_idx ON public.uploads USING btree (id, user_cs, upload_type);


--
-- Name: activators tr_activators_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_activators_bi BEFORE INSERT ON public.activators FOR EACH ROW EXECUTE FUNCTION public.tf_activators_bi();


--
-- Name: callsigns_rda tr_callsigns_rda_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_callsigns_rda_bi BEFORE INSERT ON public.callsigns_rda FOR EACH ROW EXECUTE FUNCTION public.tf_callsigns_rda_bi();


--
-- Name: cfm_qsl_qso tr_cfm_qsl_qso_bu; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_cfm_qsl_qso_bu BEFORE UPDATE ON public.cfm_qsl_qso FOR EACH ROW EXECUTE FUNCTION public.tf_cfm_qsl_qso_bu();


--
-- Name: cfm_request_qso tr_cfm_requests_qso_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_cfm_requests_qso_bi BEFORE INSERT ON public.cfm_request_qso FOR EACH ROW EXECUTE FUNCTION public.tf_cfm_request_qso_bi();


--
-- Name: cfm_qsl_qso tr_cmf_qsl_qso_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_cmf_qsl_qso_bi BEFORE INSERT ON public.cfm_qsl_qso FOR EACH ROW EXECUTE FUNCTION public.tf_cfm_qsl_qso_bi();


--
-- Name: old_callsigns tr_old_callsigns_aiu; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_old_callsigns_aiu AFTER INSERT OR UPDATE ON public.old_callsigns FOR EACH ROW EXECUTE FUNCTION public.tf_old_callsigns_aiu();


--
-- Name: qso tr_qso_ai; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_qso_ai AFTER INSERT ON public.qso FOR EACH ROW EXECUTE FUNCTION public.tf_qso_ai();


--
-- Name: qso tr_qso_au; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_qso_au AFTER UPDATE ON public.qso FOR EACH ROW EXECUTE FUNCTION public.tf_qso_au();


--
-- Name: qso tr_qso_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_qso_bi BEFORE INSERT ON public.qso FOR EACH ROW EXECUTE FUNCTION public.tf_qso_bi();


--
-- Name: activators activators_upload_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activators
    ADD CONSTRAINT activators_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES public.uploads(id);


--
-- Name: cfm_qsl_qso cfm_qsl_qso_qsl_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cfm_qsl_qso
    ADD CONSTRAINT cfm_qsl_qso_qsl_id_fkey FOREIGN KEY (qsl_id) REFERENCES public.cfm_qsl(id);


--
-- Name: cfm_qsl cfm_qsl_user_cs_fk; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cfm_qsl
    ADD CONSTRAINT cfm_qsl_user_cs_fk FOREIGN KEY (user_cs) REFERENCES public.users(callsign);


--
-- Name: country_prefixes country_prefixes_country_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.country_prefixes
    ADD CONSTRAINT country_prefixes_country_id_fkey FOREIGN KEY (country_id) REFERENCES public.countries(id);


--
-- Name: ext_loggers ext_loggers_callsign_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ext_loggers
    ADD CONSTRAINT ext_loggers_callsign_fkey FOREIGN KEY (callsign) REFERENCES public.users(callsign);


--
-- Name: qso qso_rda_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.qso
    ADD CONSTRAINT qso_rda_fkey FOREIGN KEY (rda) REFERENCES public.rda(rda);


--
-- Name: qso qso_upload_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.qso
    ADD CONSTRAINT qso_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES public.uploads(id);


--
-- Name: uploads uploads_ext_loggers_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.uploads
    ADD CONSTRAINT uploads_ext_loggers_fkey FOREIGN KEY (ext_logger_id) REFERENCES public.ext_loggers(id);


--
-- Name: FUNCTION build_activators_rating(); Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON FUNCTION public.build_activators_rating() TO "www-group";


--
-- Name: FUNCTION build_rankings_data(); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION public.build_rankings_data() FROM PUBLIC;
GRANT ALL ON FUNCTION public.build_rankings_data() TO "www-group";


--
-- Name: FUNCTION check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying); Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON FUNCTION public.check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying) TO "www-group";


--
-- Name: FUNCTION tf_activators_bi(); Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON FUNCTION public.tf_activators_bi() TO "www-group";


--
-- Name: FUNCTION tf_callsigns_rda_bi(); Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON FUNCTION public.tf_callsigns_rda_bi() TO "www-group";


--
-- Name: FUNCTION tf_cfm_qsl_qso_bi(); Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON FUNCTION public.tf_cfm_qsl_qso_bi() TO "www-group";


--
-- Name: FUNCTION tf_qso_bi(); Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON FUNCTION public.tf_qso_bi() TO "www-group";


--
-- Name: TABLE activators; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.activators TO "www-group";


--
-- Name: TABLE activators_rating; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.activators_rating TO "www-group";


--
-- Name: TABLE activators_rating_detail; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.activators_rating_detail TO www;


--
-- Name: TABLE callsigns_countries; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.callsigns_countries TO "www-group";


--
-- Name: TABLE callsigns_meta; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.callsigns_meta TO "www-group";


--
-- Name: TABLE callsigns_rda; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.callsigns_rda TO "www-group";


--
-- Name: SEQUENCE callsigns_rda_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.callsigns_rda_id_seq TO "www-group";


--
-- Name: TABLE cfm_qsl; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.cfm_qsl TO "www-group";


--
-- Name: SEQUENCE cfm_qsl_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.cfm_qsl_id_seq TO "www-group";


--
-- Name: TABLE cfm_qsl_qso; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.cfm_qsl_qso TO "www-group";


--
-- Name: SEQUENCE cfm_qsl_qso_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.cfm_qsl_qso_id_seq TO "www-group";


--
-- Name: TABLE cfm_request_blacklist; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.cfm_request_blacklist TO "www-group";


--
-- Name: TABLE cfm_request_qso; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.cfm_request_qso TO "www-group";


--
-- Name: SEQUENCE cfm_request_qso_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.cfm_request_qso_id_seq TO "www-group";


--
-- Name: TABLE cfm_requests; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.cfm_requests TO "www-group";


--
-- Name: SEQUENCE countries_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.countries_id_seq TO "www-group";


--
-- Name: TABLE countries; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.countries TO "www-group";


--
-- Name: TABLE country_prefixes; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.country_prefixes TO "www-group";


--
-- Name: TABLE ext_loggers; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.ext_loggers TO "www-group";


--
-- Name: SEQUENCE ext_loggers_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.ext_loggers_id_seq TO "www-group";


--
-- Name: TABLE old_callsigns; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE public.old_callsigns TO "www-group";


--
-- Name: TABLE old_rda; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.old_rda TO "www-group";


--
-- Name: TABLE qso; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.qso TO "www-group";


--
-- Name: SEQUENCE qso_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.qso_id_seq TO "www-group";


--
-- Name: TABLE ra_t; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.ra_t TO "www-group";


--
-- Name: TABLE rankings; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,DELETE,TRIGGER,UPDATE ON TABLE public.rankings TO "www-group";


--
-- Name: TABLE rda; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.rda TO "www-group";


--
-- Name: TABLE rda_activator; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.rda_activator TO "www-group";


--
-- Name: TABLE rda_hunter; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.rda_hunter TO "www-group";


--
-- Name: TABLE stat_log; Type: ACL; Schema: public; Owner: postgres
--

GRANT INSERT ON TABLE public.stat_log TO "www-group";


--
-- Name: TABLE stations_blacklist; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE public.stations_blacklist TO "www-group";


--
-- Name: TABLE uploads; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE public.uploads TO "www-group";


--
-- Name: SEQUENCE uploads_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.uploads_id_seq TO "www-group";


--
-- Name: TABLE users; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.users TO "www-group";


--
-- PostgreSQL database dump complete
--

