--
-- PostgreSQL database dump
--

-- Dumped from database version 9.6.17
-- Dumped by pg_dump version 9.6.17

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
-- Name: plpgsql; Type: EXTENSION; Schema: -; Owner: 
--

CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;


--
-- Name: EXTENSION plpgsql; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION plpgsql IS 'PL/pgSQL procedural language';


--
-- Name: build_rankings(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.build_rankings() RETURNS void
    LANGUAGE plpgsql
    AS $$
declare _9band_tr smallint;
begin

-- rda

delete from rda_activator;
lock table rda_hunter in share row exclusive mode;
delete from rda_hunter;

insert into rda_hunter (hunter, mode, band, rda)
select distinct callsign, mode, band, rda from qso;

insert into rda_activator (activator, rda, mode, band, callsigns)
select activator, rda, mode, band, count(distinct (callsign, dt)) as callsigns from
(select upload_id, mode, band, rda, callsign, dt
from qso) as qso join activators on qso.upload_id = activators.upload_id
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


end$$;


ALTER FUNCTION public.build_rankings() OWNER TO postgres;

--
-- Name: check_qso(character varying, character varying, character, character, character, timestamp without time zone); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying) RETURNS record
    LANGUAGE plpgsql
    AS $$
declare 
  str_callsign character varying(32);
begin
  str_callsign = strip_callsign(_callsign);
  if str_callsign is null or str_callsign = strip_callsign(_station_callsign)
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
	(dt_start < _ts or dt_start is null) and
	(dt_stop > _ts or dt_stop is null);
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
  if exists (select from qso where qso.callsign = str_callsign and qso.station_callsign = _station_callsign 
    and qso.rda = new_rda and qso.mode = _mode and qso.band = _band and 
    qso.tstamp between (_ts - interval '5 min') and (_ts + interval '5 min'))
  then
      raise exception using
            errcode='CR001',
            message='cfmrda_db_error:Связь уже внесена в базу данных';
  end if;
 end$$;


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
-- Name: strip_callsign(character varying); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.strip_callsign(callsign character varying) RETURNS character varying
    LANGUAGE plpgsql IMMUTABLE
    AS $$begin
  return substring(callsign from '\d?[A-Z]+\d+[A-Z]+');
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
    AS $$begin
  if exists (select from qso where qso.callsign = new.callsign and qso.rda = new.rda and qso.band = new.band and qso.mode = new.mode) then
    raise 'cfmrda_db_error:Этот RDA у вас уже подтвержден ⇒ <b>(%, %, %)</b> ⇐ This RDA is already comfirmed for you.', new.rda, new.mode, new.band || 'MHz';
  end if;
  perform check_qso(new.callsign, new.station_callsign, new.rda, new.band, new.mode, new.tstamp);
/*  if exists (select 1 from cfm_qsl_qso
	where callsign = new.callsign and rda = new.rda
	and station_callsign = new.station_callsign
	and band = new.band and mode = new.mode) then
    return null;
   end if;   */
   return new;
 end$$;


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
  if not exists (select from rda_hunter where rda = new.rda and hunter = new.callsign and mode = new.mode and band = new.band)
  then
    insert into rda_hunter values (new.callsign, new.rda, new.band, new.mode);
  end if;
  return new;
 end$$;


ALTER FUNCTION public.tf_qso_ai() OWNER TO postgres;

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
  return new;
 end$$;


ALTER FUNCTION public.tf_qso_bi() OWNER TO postgres;

SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: activators; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.activators (
    upload_id bigint NOT NULL,
    activator character varying(32) NOT NULL
);


ALTER TABLE public.activators OWNER TO postgres;

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
    admin character varying(64),
    status_date timestamp without time zone,
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
    viewed boolean DEFAULT false,
    comment character varying(256),
    state boolean,
    user_cs character varying(32),
    status_tstamp timestamp without time zone DEFAULT now()
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
-- Name: list_bands; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.list_bands (
    band character varying(16) NOT NULL
);


ALTER TABLE public.list_bands OWNER TO postgres;

--
-- Name: list_modes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.list_modes (
    mode character varying(16) NOT NULL
);


ALTER TABLE public.list_modes OWNER TO postgres;

--
-- Name: list_rda; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.list_rda (
    rda character(5) NOT NULL
);


ALTER TABLE public.list_rda OWNER TO postgres;

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
    rec_ts timestamp without time zone DEFAULT now()
);


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
-- Name: rankings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rankings (
    role character varying(16) NOT NULL,
    mode character varying(16) NOT NULL,
    band character varying(8) NOT NULL,
    callsign character varying(32) NOT NULL,
    _count integer,
    _rank integer,
    _row integer
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
-- Name: ext_loggers ext_loggers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ext_loggers
    ADD CONSTRAINT ext_loggers_pkey PRIMARY KEY (id);


--
-- Name: list_bands list_bands_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.list_bands
    ADD CONSTRAINT list_bands_pkey PRIMARY KEY (band);


--
-- Name: list_modes list_modes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.list_modes
    ADD CONSTRAINT list_modes_pkey PRIMARY KEY (mode);


--
-- Name: list_rda list_rda_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.list_rda
    ADD CONSTRAINT list_rda_pkey PRIMARY KEY (rda);


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
-- Name: uploads uploads_hash_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.uploads
    ADD CONSTRAINT uploads_hash_key UNIQUE (hash);


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
-- Name: cfm_qsl_qso_status_date_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX cfm_qsl_qso_status_date_idx ON public.cfm_qsl_qso USING btree (status_date);


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
-- Name: fki_uploads_ext_loggers_fkey; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX fki_uploads_ext_loggers_fkey ON public.uploads USING btree (ext_logger_id);


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
-- Name: qso_callsign_mode_band_rda_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX qso_callsign_mode_band_rda_idx ON public.qso USING btree (callsign, mode, band, rda);


--
-- Name: qso_upload_id_mode_band_rda_callsign_dt_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX qso_upload_id_mode_band_rda_callsign_dt_idx ON public.qso USING btree (upload_id, mode, band, rda, callsign, dt);


--
-- Name: rankings_callsign_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX rankings_callsign_idx ON public.rankings USING btree (callsign);


--
-- Name: rankings_role_mode_band__row_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX rankings_role_mode_band__row_idx ON public.rankings USING btree (role, mode, band, _row);


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
-- Name: uploads_enabled_id_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX uploads_enabled_id_idx ON public.uploads USING btree (enabled, id);


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

CREATE TRIGGER tr_activators_bi BEFORE INSERT ON public.activators FOR EACH ROW EXECUTE PROCEDURE public.tf_activators_bi();


--
-- Name: callsigns_rda tr_callsigns_rda_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_callsigns_rda_bi BEFORE INSERT ON public.callsigns_rda FOR EACH ROW EXECUTE PROCEDURE public.tf_callsigns_rda_bi();


--
-- Name: cfm_qsl_qso tr_cfm_qsl_qso_bu; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_cfm_qsl_qso_bu BEFORE UPDATE ON public.cfm_qsl_qso FOR EACH ROW EXECUTE PROCEDURE public.tf_cfm_qsl_qso_bu();


--
-- Name: cfm_request_qso tr_cfm_requests_qso_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_cfm_requests_qso_bi BEFORE INSERT ON public.cfm_request_qso FOR EACH ROW EXECUTE PROCEDURE public.tf_cfm_request_qso_bi();


--
-- Name: cfm_qsl_qso tr_cmf_qsl_qso_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_cmf_qsl_qso_bi BEFORE INSERT ON public.cfm_qsl_qso FOR EACH ROW EXECUTE PROCEDURE public.tf_cfm_qsl_qso_bi();


--
-- Name: old_callsigns tr_old_callsigns_aiu; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_old_callsigns_aiu AFTER INSERT OR UPDATE ON public.old_callsigns FOR EACH ROW EXECUTE PROCEDURE public.tf_old_callsigns_aiu();


--
-- Name: qso tr_qso_ai; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_qso_ai AFTER INSERT ON public.qso FOR EACH ROW EXECUTE PROCEDURE public.tf_qso_ai();

ALTER TABLE public.qso DISABLE TRIGGER tr_qso_ai;


--
-- Name: qso tr_qso_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_qso_bi BEFORE INSERT ON public.qso FOR EACH ROW EXECUTE PROCEDURE public.tf_qso_bi();


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
-- Name: TABLE ext_loggers; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE public.ext_loggers TO "www-group";


--
-- Name: SEQUENCE ext_loggers_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.ext_loggers_id_seq TO "www-group";


--
-- Name: TABLE list_bands; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE public.list_bands TO "www-group";


--
-- Name: TABLE list_modes; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE public.list_modes TO "www-group";


--
-- Name: TABLE list_rda; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE public.list_rda TO "www-group";


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
-- Name: TABLE rankings; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,DELETE,TRIGGER ON TABLE public.rankings TO "www-group";


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

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.users TO "www-group";


--
-- PostgreSQL database dump complete
--

