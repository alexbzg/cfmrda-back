--
-- PostgreSQL database dump
--

SET statement_timeout = 0;
SET lock_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET client_min_messages = warning;

--
-- Name: plpgsql; Type: EXTENSION; Schema: -; Owner: 
--

CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;


--
-- Name: EXTENSION plpgsql; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION plpgsql IS 'PL/pgSQL procedural language';


SET search_path = public, pg_catalog;

--
-- Name: build_rankings(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION build_rankings() RETURNS void
    LANGUAGE plpgsql
    AS $$
declare _9band_tr smallint;
begin

-- rda

delete from rda_activator;
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

CREATE FUNCTION check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying) RETURNS record
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
    where old_rda.old = _rda;
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
    and qso.rda = new_rda and qso.mode = _mode and qso.band = _band and qso.tstamp = _ts)
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

CREATE FUNCTION hunters_rdas() RETURNS TABLE(callsign character varying, rda character)
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

CREATE FUNCTION rankings_json(condition character varying) RETURNS json
    LANGUAGE plpgsql
    AS $$declare 
  data json;
begin
  execute 'select json_object_agg(role, data) as data from ' 
	|| '(select role, json_object_agg(mode, data) as data from '
	|| '(select role, mode, json_object_agg(band, data) as data from '
	|| '(select role, mode, band, json_agg(json_build_object(''callsign'', callsign, '
	|| '''count'', _count, ''rank'', _rank, ''row'', _row)) as data from '
	|| '(select * from rankings where ' || condition || ' order by _row) as l_0 '
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

CREATE FUNCTION strip_callsign(callsign character varying) RETURNS character varying
    LANGUAGE plpgsql IMMUTABLE
    AS $$begin
  return substring(callsign from '\d?[A-Z]+\d+[A-Z]+');
end$$;


ALTER FUNCTION public.strip_callsign(callsign character varying) OWNER TO postgres;

--
-- Name: tf_activators_bi(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION tf_activators_bi() RETURNS trigger
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

CREATE FUNCTION tf_callsigns_rda_bi() RETURNS trigger
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
  if exists (select from old_rda where old_rda.old = new.rda and old_rda.new is not null)
  then  
    select old_rda.new from old_rda where old_rda.old = new.rda
      into new.rda;
  end if;  
  if not exists (select from rda where rda = new.rda)
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

CREATE FUNCTION tf_cfm_qsl_qso_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
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

CREATE FUNCTION tf_cfm_qsl_qso_bu() RETURNS trigger
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

CREATE FUNCTION tf_cfm_request_qso_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  perform check_qso(new.callsign, new.station_callsign, new.rda, new.band, new.mode, new.tstamp);
  return new;
 end$$;


ALTER FUNCTION public.tf_cfm_request_qso_bi() OWNER TO postgres;

--
-- Name: tf_old_callsigns_aiu(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION tf_old_callsigns_aiu() RETURNS trigger
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

CREATE FUNCTION tf_qso_ai() RETURNS trigger
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

CREATE FUNCTION tf_qso_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
declare 
  new_callsign character varying(32);
begin
  select * from check_qso(new.callsign, new.station_callsign, new.rda, new.band, new.mode, new.tstamp)
    into new_callsign, new.rda;
  if new_callsign <> strip_callsign(new.callsign)
  then
    new.old_callsign = strip_callsign(new.callsign);
    new.callsign = new_callsign;
  end if;
  new.dt = date(new.tstamp);
  return new;
 end$$;


ALTER FUNCTION public.tf_qso_bi() OWNER TO postgres;

SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: activators; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE activators (
    upload_id bigint NOT NULL,
    activator character varying(32) NOT NULL
);


ALTER TABLE activators OWNER TO postgres;

--
-- Name: callsigns_rda; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE callsigns_rda (
    callsign character varying(64) NOT NULL,
    dt_start date,
    dt_stop date,
    source character varying(64),
    ts timestamp without time zone DEFAULT now() NOT NULL,
    rda character(5) NOT NULL,
    id integer NOT NULL,
    comment character varying(256)
);


ALTER TABLE callsigns_rda OWNER TO postgres;

--
-- Name: callsigns_rda_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE callsigns_rda_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE callsigns_rda_id_seq OWNER TO postgres;

--
-- Name: callsigns_rda_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE callsigns_rda_id_seq OWNED BY callsigns_rda.id;


--
-- Name: cfm_qsl_qso; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE cfm_qsl_qso (
    id integer NOT NULL,
    station_callsign character varying(32),
    rda character(5) NOT NULL,
    band character varying(16) NOT NULL,
    mode character varying(16) NOT NULL,
    callsign character varying(32) NOT NULL,
    new_callsign character varying(32),
    tstamp timestamp without time zone NOT NULL,
    image character varying(128) NOT NULL,
    user_cs character varying(32) NOT NULL,
    state boolean,
    comment character varying(256),
    admin character varying(64),
    status_date timestamp without time zone
);


ALTER TABLE cfm_qsl_qso OWNER TO postgres;

--
-- Name: cfm_qsl_qso_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE cfm_qsl_qso_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE cfm_qsl_qso_id_seq OWNER TO postgres;

--
-- Name: cfm_qsl_qso_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE cfm_qsl_qso_id_seq OWNED BY cfm_qsl_qso.id;


--
-- Name: cfm_request_blacklist; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE cfm_request_blacklist (
    callsign character varying(32) NOT NULL
);


ALTER TABLE cfm_request_blacklist OWNER TO postgres;

--
-- Name: cfm_request_qso; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE cfm_request_qso (
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


ALTER TABLE cfm_request_qso OWNER TO postgres;

--
-- Name: cfm_request_qso_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE cfm_request_qso_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE cfm_request_qso_id_seq OWNER TO postgres;

--
-- Name: cfm_request_qso_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE cfm_request_qso_id_seq OWNED BY cfm_request_qso.id;


--
-- Name: cfm_requests; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE cfm_requests (
    callsign character varying(32) NOT NULL,
    tstamp timestamp without time zone
);


ALTER TABLE cfm_requests OWNER TO postgres;

--
-- Name: ext_loggers; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE ext_loggers (
    callsign character varying(32) NOT NULL,
    logger character varying(8) NOT NULL,
    login_data json,
    state integer,
    qso_count integer,
    last_updated date,
    id integer NOT NULL
);


ALTER TABLE ext_loggers OWNER TO postgres;

--
-- Name: ext_loggers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE ext_loggers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ext_loggers_id_seq OWNER TO postgres;

--
-- Name: ext_loggers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE ext_loggers_id_seq OWNED BY ext_loggers.id;


--
-- Name: list_bands; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE list_bands (
    band character varying(16) NOT NULL
);


ALTER TABLE list_bands OWNER TO postgres;

--
-- Name: list_modes; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE list_modes (
    mode character varying(16) NOT NULL
);


ALTER TABLE list_modes OWNER TO postgres;

--
-- Name: list_rda; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE list_rda (
    rda character(5) NOT NULL
);


ALTER TABLE list_rda OWNER TO postgres;

--
-- Name: old_callsigns; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE old_callsigns (
    old character varying(32) NOT NULL,
    new character varying(32) NOT NULL,
    confirmed boolean
);


ALTER TABLE old_callsigns OWNER TO postgres;

--
-- Name: old_rda; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE old_rda (
    old character varying(5) NOT NULL,
    new character varying(5)
);


ALTER TABLE old_rda OWNER TO postgres;

--
-- Name: qso; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE qso (
    id integer NOT NULL,
    upload_id integer,
    callsign character varying(32) NOT NULL,
    station_callsign character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(8) NOT NULL,
    mode character varying(16) NOT NULL,
    tstamp timestamp without time zone NOT NULL,
    dt date DEFAULT date(now()) NOT NULL,
    old_callsign character varying(32)
);


ALTER TABLE qso OWNER TO postgres;

--
-- Name: qso_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE qso_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE qso_id_seq OWNER TO postgres;

--
-- Name: qso_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE qso_id_seq OWNED BY qso.id;


--
-- Name: rankings; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE rankings (
    role character varying(16) NOT NULL,
    mode character varying(16) NOT NULL,
    band character varying(8) NOT NULL,
    callsign character varying(32) NOT NULL,
    _count integer,
    _rank integer,
    _row integer
);


ALTER TABLE rankings OWNER TO postgres;

--
-- Name: rda; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE rda (
    rda character(5) NOT NULL
);


ALTER TABLE rda OWNER TO postgres;

--
-- Name: rda_activator; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE rda_activator (
    activator character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(8) NOT NULL,
    mode character varying(16) NOT NULL,
    callsigns bigint
);


ALTER TABLE rda_activator OWNER TO postgres;

--
-- Name: rda_hunter; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE rda_hunter (
    hunter character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(16),
    mode character varying(16)
);


ALTER TABLE rda_hunter OWNER TO postgres;

--
-- Name: uploads; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE uploads (
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


ALTER TABLE uploads OWNER TO postgres;

--
-- Name: uploads_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE uploads_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE uploads_id_seq OWNER TO postgres;

--
-- Name: uploads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE uploads_id_seq OWNED BY uploads.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE users (
    callsign character varying(32) NOT NULL,
    password character varying(32) NOT NULL,
    email character varying(64) NOT NULL,
    email_confirmed boolean DEFAULT false NOT NULL
);


ALTER TABLE users OWNER TO postgres;

--
-- Name: id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY callsigns_rda ALTER COLUMN id SET DEFAULT nextval('callsigns_rda_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY cfm_qsl_qso ALTER COLUMN id SET DEFAULT nextval('cfm_qsl_qso_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY cfm_request_qso ALTER COLUMN id SET DEFAULT nextval('cfm_request_qso_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY ext_loggers ALTER COLUMN id SET DEFAULT nextval('ext_loggers_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY qso ALTER COLUMN id SET DEFAULT nextval('qso_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY uploads ALTER COLUMN id SET DEFAULT nextval('uploads_id_seq'::regclass);


--
-- Name: activators_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY activators
    ADD CONSTRAINT activators_pkey PRIMARY KEY (upload_id, activator);


--
-- Name: callsigns_rda_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY callsigns_rda
    ADD CONSTRAINT callsigns_rda_pkey PRIMARY KEY (id);


--
-- Name: cfm_qsl_qso_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY cfm_qsl_qso
    ADD CONSTRAINT cfm_qsl_qso_pkey PRIMARY KEY (id);


--
-- Name: cfm_request_blacklist_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY cfm_request_blacklist
    ADD CONSTRAINT cfm_request_blacklist_pkey PRIMARY KEY (callsign);


--
-- Name: cfm_request_qso_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY cfm_request_qso
    ADD CONSTRAINT cfm_request_qso_pkey PRIMARY KEY (id);


--
-- Name: ext_loggers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY ext_loggers
    ADD CONSTRAINT ext_loggers_pkey PRIMARY KEY (id);


--
-- Name: list_bands_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY list_bands
    ADD CONSTRAINT list_bands_pkey PRIMARY KEY (band);


--
-- Name: list_modes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY list_modes
    ADD CONSTRAINT list_modes_pkey PRIMARY KEY (mode);


--
-- Name: list_rda_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY list_rda
    ADD CONSTRAINT list_rda_pkey PRIMARY KEY (rda);


--
-- Name: old_callsigns_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY old_callsigns
    ADD CONSTRAINT old_callsigns_pkey PRIMARY KEY (old, new);


--
-- Name: old_rda_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY old_rda
    ADD CONSTRAINT old_rda_pkey PRIMARY KEY (old);


--
-- Name: qso_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY qso
    ADD CONSTRAINT qso_pkey PRIMARY KEY (id);


--
-- Name: qso_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY cfm_requests
    ADD CONSTRAINT qso_requests_pkey PRIMARY KEY (callsign);


--
-- Name: rankings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY rankings
    ADD CONSTRAINT rankings_pkey PRIMARY KEY (role, mode, band, callsign);


--
-- Name: rda_activator_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY rda_activator
    ADD CONSTRAINT rda_activator_pkey PRIMARY KEY (activator, rda, band, mode);


--
-- Name: rda_hunter_uq; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY rda_hunter
    ADD CONSTRAINT rda_hunter_uq UNIQUE (hunter, rda, band, mode);


--
-- Name: rda_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY rda
    ADD CONSTRAINT rda_pkey PRIMARY KEY (rda);


--
-- Name: uploads_hash_key; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY uploads
    ADD CONSTRAINT uploads_hash_key UNIQUE (hash);


--
-- Name: uploads_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY uploads
    ADD CONSTRAINT uploads_pkey PRIMARY KEY (id);


--
-- Name: users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY users
    ADD CONSTRAINT users_pkey PRIMARY KEY (callsign);


--
-- Name: activators_activator_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX activators_activator_idx ON activators USING btree (activator);


--
-- Name: callsigns_rda_callsign_dt_start_dt_stop_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX callsigns_rda_callsign_dt_start_dt_stop_idx ON callsigns_rda USING btree (callsign, dt_start, dt_stop);


--
-- Name: cfm_qsl_qso_status_date_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX cfm_qsl_qso_status_date_idx ON cfm_qsl_qso USING btree (status_date);


--
-- Name: cfm_qsl_qso_user_cs_fkey; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX cfm_qsl_qso_user_cs_fkey ON cfm_qsl_qso USING btree (user_cs);


--
-- Name: cfm_request_qso_correspondent_callsign_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX cfm_request_qso_correspondent_callsign_idx ON cfm_request_qso USING btree (correspondent);


--
-- Name: cfm_request_qso_sent_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX cfm_request_qso_sent_idx ON cfm_request_qso USING btree (sent);


--
-- Name: cfm_request_qso_user_cs_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX cfm_request_qso_user_cs_idx ON cfm_request_qso USING btree (user_cs);


--
-- Name: fki_qso_rda_fkey; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX fki_qso_rda_fkey ON qso USING btree (rda);


--
-- Name: fki_uploads_ext_loggers_fkey; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX fki_uploads_ext_loggers_fkey ON uploads USING btree (ext_logger_id);


--
-- Name: old_callsigns_confirmed_new_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX old_callsigns_confirmed_new_idx ON old_callsigns USING btree (confirmed, new);


--
-- Name: old_callsigns_confirmed_old_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX old_callsigns_confirmed_old_idx ON old_callsigns USING btree (confirmed, old);


--
-- Name: old_callsigns_uq; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE UNIQUE INDEX old_callsigns_uq ON old_callsigns USING btree (old) WHERE confirmed;


--
-- Name: qso_callsign_mode_band_rda_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_callsign_mode_band_rda_idx ON qso USING btree (callsign, mode, band, rda);


--
-- Name: qso_upload_id_mode_band_rda_callsign_dt_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_upload_id_mode_band_rda_callsign_dt_idx ON qso USING btree (upload_id, mode, band, rda, callsign, dt);


--
-- Name: rankings_callsign_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX rankings_callsign_idx ON rankings USING btree (callsign);


--
-- Name: rankings_role_mode_band__row_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX rankings_role_mode_band__row_idx ON rankings USING btree (role, mode, band, _row);


--
-- Name: rankings_top100; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX rankings_top100 ON rankings USING btree (role, mode, band, callsign, _count, _rank) WHERE (_rank < 101);


--
-- Name: rda_activator_activator_rda_band_mode_callsigns_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX rda_activator_activator_rda_band_mode_callsigns_idx ON rda_activator USING btree (activator, rda, band, mode, callsigns);


--
-- Name: rda_hunter_callsign_rda_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX rda_hunter_callsign_rda_idx ON rda_hunter USING btree (hunter, rda);


--
-- Name: rda_hunter_hunter_band_mode_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX rda_hunter_hunter_band_mode_idx ON rda_hunter USING btree (hunter, band, mode);


--
-- Name: rda_hunter_hunter_mode_band_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX rda_hunter_hunter_mode_band_idx ON rda_hunter USING btree (hunter, mode, band);


--
-- Name: rda_hunter_hunter_mode_band_rda_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX rda_hunter_hunter_mode_band_rda_idx ON rda_hunter USING btree (hunter, mode, band, rda);


--
-- Name: unique_callsigns_rda_qrz; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE UNIQUE INDEX unique_callsigns_rda_qrz ON callsigns_rda USING btree (callsign) WHERE ((source)::text = 'QRZ.ru'::text);


--
-- Name: uploads_enabled_id_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX uploads_enabled_id_idx ON uploads USING btree (enabled, id);


--
-- Name: uploads_id_enabled_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX uploads_id_enabled_idx ON uploads USING btree (id, enabled);


--
-- Name: uploads_id_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX uploads_id_idx ON uploads USING btree (id);


--
-- Name: uploads_id_user_cs_upload_type_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX uploads_id_user_cs_upload_type_idx ON uploads USING btree (id, user_cs, upload_type);


--
-- Name: tr_activators_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_activators_bi BEFORE INSERT ON activators FOR EACH ROW EXECUTE PROCEDURE tf_activators_bi();


--
-- Name: tr_callsigns_rda_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_callsigns_rda_bi BEFORE INSERT ON callsigns_rda FOR EACH ROW EXECUTE PROCEDURE tf_callsigns_rda_bi();


--
-- Name: tr_cfm_qsl_qso_bu; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_cfm_qsl_qso_bu BEFORE UPDATE ON cfm_qsl_qso FOR EACH ROW EXECUTE PROCEDURE tf_cfm_qsl_qso_bu();


--
-- Name: tr_cfm_requests_qso_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_cfm_requests_qso_bi BEFORE INSERT ON cfm_request_qso FOR EACH ROW EXECUTE PROCEDURE tf_cfm_request_qso_bi();


--
-- Name: tr_cmf_qsl_qso_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_cmf_qsl_qso_bi BEFORE INSERT ON cfm_qsl_qso FOR EACH ROW EXECUTE PROCEDURE tf_cfm_qsl_qso_bi();


--
-- Name: tr_old_callsigns_aiu; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_old_callsigns_aiu AFTER INSERT OR UPDATE ON old_callsigns FOR EACH ROW EXECUTE PROCEDURE tf_old_callsigns_aiu();


--
-- Name: tr_qso_ai; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_qso_ai AFTER INSERT ON qso FOR EACH ROW EXECUTE PROCEDURE tf_qso_ai();


--
-- Name: tr_qso_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_qso_bi BEFORE INSERT ON qso FOR EACH ROW EXECUTE PROCEDURE tf_qso_bi();


--
-- Name: activators_upload_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY activators
    ADD CONSTRAINT activators_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES uploads(id);


--
-- Name: cfm_qsl_qso_user_cs_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY cfm_qsl_qso
    ADD CONSTRAINT cfm_qsl_qso_user_cs_fkey FOREIGN KEY (user_cs) REFERENCES users(callsign);


--
-- Name: ext_loggers_callsign_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY ext_loggers
    ADD CONSTRAINT ext_loggers_callsign_fkey FOREIGN KEY (callsign) REFERENCES users(callsign);


--
-- Name: qso_rda_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY qso
    ADD CONSTRAINT qso_rda_fkey FOREIGN KEY (rda) REFERENCES rda(rda);


--
-- Name: qso_upload_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY qso
    ADD CONSTRAINT qso_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES uploads(id);


--
-- Name: uploads_ext_loggers_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY uploads
    ADD CONSTRAINT uploads_ext_loggers_fkey FOREIGN KEY (ext_logger_id) REFERENCES ext_loggers(id);


--
-- Name: public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM postgres;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- Name: check_qso(character varying, character varying, character, character, character, timestamp without time zone); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying) FROM PUBLIC;
REVOKE ALL ON FUNCTION check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying) FROM postgres;
GRANT ALL ON FUNCTION check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying) TO postgres;
GRANT ALL ON FUNCTION check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying) TO PUBLIC;
GRANT ALL ON FUNCTION check_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character, _mode character, _ts timestamp without time zone, OUT new_callsign character varying, OUT new_rda character varying) TO "www-group";


--
-- Name: tf_activators_bi(); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION tf_activators_bi() FROM PUBLIC;
REVOKE ALL ON FUNCTION tf_activators_bi() FROM postgres;
GRANT ALL ON FUNCTION tf_activators_bi() TO postgres;
GRANT ALL ON FUNCTION tf_activators_bi() TO PUBLIC;
GRANT ALL ON FUNCTION tf_activators_bi() TO "www-group";


--
-- Name: tf_callsigns_rda_bi(); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION tf_callsigns_rda_bi() FROM PUBLIC;
REVOKE ALL ON FUNCTION tf_callsigns_rda_bi() FROM postgres;
GRANT ALL ON FUNCTION tf_callsigns_rda_bi() TO postgres;
GRANT ALL ON FUNCTION tf_callsigns_rda_bi() TO PUBLIC;
GRANT ALL ON FUNCTION tf_callsigns_rda_bi() TO "www-group";


--
-- Name: tf_cfm_qsl_qso_bi(); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION tf_cfm_qsl_qso_bi() FROM PUBLIC;
REVOKE ALL ON FUNCTION tf_cfm_qsl_qso_bi() FROM postgres;
GRANT ALL ON FUNCTION tf_cfm_qsl_qso_bi() TO postgres;
GRANT ALL ON FUNCTION tf_cfm_qsl_qso_bi() TO PUBLIC;
GRANT ALL ON FUNCTION tf_cfm_qsl_qso_bi() TO "www-group";


--
-- Name: tf_qso_bi(); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION tf_qso_bi() FROM PUBLIC;
REVOKE ALL ON FUNCTION tf_qso_bi() FROM postgres;
GRANT ALL ON FUNCTION tf_qso_bi() TO postgres;
GRANT ALL ON FUNCTION tf_qso_bi() TO PUBLIC;
GRANT ALL ON FUNCTION tf_qso_bi() TO "www-group";


--
-- Name: activators; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE activators FROM PUBLIC;
REVOKE ALL ON TABLE activators FROM postgres;
GRANT ALL ON TABLE activators TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE activators TO "www-group";


--
-- Name: callsigns_rda; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE callsigns_rda FROM PUBLIC;
REVOKE ALL ON TABLE callsigns_rda FROM postgres;
GRANT ALL ON TABLE callsigns_rda TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE callsigns_rda TO "www-group";


--
-- Name: callsigns_rda_id_seq; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON SEQUENCE callsigns_rda_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE callsigns_rda_id_seq FROM postgres;
GRANT ALL ON SEQUENCE callsigns_rda_id_seq TO postgres;
GRANT ALL ON SEQUENCE callsigns_rda_id_seq TO "www-group";


--
-- Name: cfm_qsl_qso; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE cfm_qsl_qso FROM PUBLIC;
REVOKE ALL ON TABLE cfm_qsl_qso FROM postgres;
GRANT ALL ON TABLE cfm_qsl_qso TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE cfm_qsl_qso TO "www-group";


--
-- Name: cfm_qsl_qso_id_seq; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON SEQUENCE cfm_qsl_qso_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE cfm_qsl_qso_id_seq FROM postgres;
GRANT ALL ON SEQUENCE cfm_qsl_qso_id_seq TO postgres;
GRANT ALL ON SEQUENCE cfm_qsl_qso_id_seq TO "www-group";


--
-- Name: cfm_request_blacklist; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE cfm_request_blacklist FROM PUBLIC;
REVOKE ALL ON TABLE cfm_request_blacklist FROM postgres;
GRANT ALL ON TABLE cfm_request_blacklist TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE cfm_request_blacklist TO "www-group";


--
-- Name: cfm_request_qso; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE cfm_request_qso FROM PUBLIC;
REVOKE ALL ON TABLE cfm_request_qso FROM postgres;
GRANT ALL ON TABLE cfm_request_qso TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE cfm_request_qso TO "www-group";


--
-- Name: cfm_request_qso_id_seq; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON SEQUENCE cfm_request_qso_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE cfm_request_qso_id_seq FROM postgres;
GRANT ALL ON SEQUENCE cfm_request_qso_id_seq TO postgres;
GRANT ALL ON SEQUENCE cfm_request_qso_id_seq TO "www-group";


--
-- Name: cfm_requests; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE cfm_requests FROM PUBLIC;
REVOKE ALL ON TABLE cfm_requests FROM postgres;
GRANT ALL ON TABLE cfm_requests TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE cfm_requests TO "www-group";


--
-- Name: ext_loggers; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE ext_loggers FROM PUBLIC;
REVOKE ALL ON TABLE ext_loggers FROM postgres;
GRANT ALL ON TABLE ext_loggers TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE ext_loggers TO "www-group";


--
-- Name: ext_loggers_id_seq; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON SEQUENCE ext_loggers_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE ext_loggers_id_seq FROM postgres;
GRANT ALL ON SEQUENCE ext_loggers_id_seq TO postgres;
GRANT ALL ON SEQUENCE ext_loggers_id_seq TO "www-group";


--
-- Name: list_bands; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE list_bands FROM PUBLIC;
REVOKE ALL ON TABLE list_bands FROM postgres;
GRANT ALL ON TABLE list_bands TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE list_bands TO "www-group";


--
-- Name: list_modes; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE list_modes FROM PUBLIC;
REVOKE ALL ON TABLE list_modes FROM postgres;
GRANT ALL ON TABLE list_modes TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE list_modes TO "www-group";


--
-- Name: list_rda; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE list_rda FROM PUBLIC;
REVOKE ALL ON TABLE list_rda FROM postgres;
GRANT ALL ON TABLE list_rda TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE list_rda TO "www-group";


--
-- Name: old_callsigns; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE old_callsigns FROM PUBLIC;
REVOKE ALL ON TABLE old_callsigns FROM postgres;
GRANT ALL ON TABLE old_callsigns TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE old_callsigns TO "www-group";


--
-- Name: old_rda; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE old_rda FROM PUBLIC;
REVOKE ALL ON TABLE old_rda FROM postgres;
GRANT ALL ON TABLE old_rda TO postgres;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE old_rda TO "www-group";


--
-- Name: qso; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE qso FROM PUBLIC;
REVOKE ALL ON TABLE qso FROM postgres;
GRANT ALL ON TABLE qso TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE qso TO "www-group";


--
-- Name: qso_id_seq; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON SEQUENCE qso_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE qso_id_seq FROM postgres;
GRANT ALL ON SEQUENCE qso_id_seq TO postgres;
GRANT ALL ON SEQUENCE qso_id_seq TO "www-group";


--
-- Name: rankings; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE rankings FROM PUBLIC;
REVOKE ALL ON TABLE rankings FROM postgres;
GRANT ALL ON TABLE rankings TO postgres;
GRANT SELECT,INSERT,DELETE,TRIGGER ON TABLE rankings TO "www-group";


--
-- Name: rda; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE rda FROM PUBLIC;
REVOKE ALL ON TABLE rda FROM postgres;
GRANT ALL ON TABLE rda TO postgres;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE rda TO "www-group";


--
-- Name: rda_activator; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE rda_activator FROM PUBLIC;
REVOKE ALL ON TABLE rda_activator FROM postgres;
GRANT ALL ON TABLE rda_activator TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE rda_activator TO "www-group";


--
-- Name: rda_hunter; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE rda_hunter FROM PUBLIC;
REVOKE ALL ON TABLE rda_hunter FROM postgres;
GRANT ALL ON TABLE rda_hunter TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,UPDATE ON TABLE rda_hunter TO "www-group";


--
-- Name: uploads; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE uploads FROM PUBLIC;
REVOKE ALL ON TABLE uploads FROM postgres;
GRANT ALL ON TABLE uploads TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,UPDATE ON TABLE uploads TO "www-group";


--
-- Name: uploads_id_seq; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON SEQUENCE uploads_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE uploads_id_seq FROM postgres;
GRANT ALL ON SEQUENCE uploads_id_seq TO postgres;
GRANT ALL ON SEQUENCE uploads_id_seq TO "www-group";


--
-- Name: users; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE users FROM PUBLIC;
REVOKE ALL ON TABLE users FROM postgres;
GRANT ALL ON TABLE users TO postgres;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE users TO "www-group";


--
-- PostgreSQL database dump complete
--

