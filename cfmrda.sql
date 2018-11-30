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
    AS $$begin
delete from rankings;
insert into rankings 
select * from
(with rda_act_m_b as (select activator, qso.rda, mode, band, count(distinct callsign)
from qso, uploads, activators
where qso.upload_id = uploads.id and enabled and activators.upload_id = qso.upload_id
group by activator, mode, band, qso.rda
having count(distinct callsign) > 99),

act_m_b as (select activator, mode, band, count(rda), rank() over (partition by mode, band order by count(rda) desc)
from rda_act_m_b
group by activator, mode, band),

rda_act_b as (select activator, qso.rda, band, count(distinct callsign)
from qso, uploads, activators
where qso.upload_id = uploads.id and enabled and activators.upload_id = qso.upload_id
group by activator, band, qso.rda
having count(distinct callsign) > 99),

act_b as (select activator, band, count(rda), rank() over (partition by band order by count(rda) desc)
from rda_act_b
group by activator, band),

rda_act_m as (select activator, qso.rda, mode, count(distinct callsign)
from qso, uploads, activators
where qso.upload_id = uploads.id and enabled and activators.upload_id = qso.upload_id
group by activator, mode, qso.rda
having count(distinct callsign) > 99),

rda_act as (select activator, qso.rda, count(distinct callsign)
from qso, uploads, activators
where qso.upload_id = uploads.id and enabled and activators.upload_id = qso.upload_id
group by activator, qso.rda
having count(distinct callsign) > 99),

rda_hnt_m_b as (select distinct callsign, qso.rda, mode, band 
from qso
where (select enabled from uploads where qso.upload_id = uploads.id) or qso.upload_id is null
union
select activator as callsign, rda, mode, band from rda_act_m_b),

hnt_m_b as (select callsign, mode, band, count(rda), rank() over (partition by mode, band order by count(rda) desc)
from rda_hnt_m_b
group by callsign, mode, band),

rda_hnt_m as (select distinct callsign, qso.rda, mode
from qso
where (select enabled from uploads where qso.upload_id = uploads.id) or qso.upload_id is null
union
select activator as callsign, rda, mode from rda_act_m),

rda_hnt_b as (select distinct callsign, qso.rda, band 
from qso
where (select enabled from uploads where qso.upload_id = uploads.id) or qso.upload_id is null
union
select activator as callsign, rda, band from rda_act_b),

hnt_b as (select callsign, band, count(rda), rank() over (partition by band order by count(rda) desc)
from rda_hnt_b
group by callsign, band),

rda_hnt as (select distinct callsign, qso.rda 
from qso, uploads 
where qso.upload_id = uploads.id and enabled
union
select activator as callsign, rda from rda_act)

select 'activator', mode, band, activator, count, rank
from act_m_b

union all

select 'activator', mode, 'bandsSum', activator, sum(count), rank() over(partition by mode order by sum(count) desc)
from act_m_b
group by activator, mode

union all

select 'activator', mode, 'total', activator, count(rda), rank() over(partition by mode order by count(rda) desc) from
rda_act_m
group by activator, mode

union all 

select 'activator', 'total', band, activator, count, rank
from act_b

union all

select 'activator', 'total', 'bandsSum', activator, sum(count), rank() over(order by sum(count) desc)
from act_b
group by activator

union all

select 'activator', 'total', 'total', activator, count(rda), rank() over(order by count(rda) desc)
from rda_act
group by activator

union all

select 'hunter', mode, band, callsign, count, rank
from hnt_m_b

union all

select 'hunter', mode, 'bandsSum', callsign, sum(count), rank() over(partition by mode order by sum(count) desc)
from hnt_m_b
group by callsign, mode

union all

select 'hunter', mode, 'total', callsign, count(rda), rank() over(partition by mode order by count(rda) desc)
from rda_hnt_m
group by callsign, mode

union all

select 'hunter', 'total', band, callsign, count, rank
from hnt_b

union all

select 'hunter', 'total', 'bandsSum', callsign, sum(count), rank() over(order by sum(count) desc)
from hnt_b
group by callsign

union all

select 'hunter', 'total', 'total', callsign, count(rda), rank() over(order by count(rda) desc)
from rda_hnt
group by callsign) as r;
end$$;


ALTER FUNCTION public.build_rankings() OWNER TO postgres;

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
	|| '''count'', _count, ''rank'', _rank)) as data from '
	|| '(select * from rankings where ' || condition || ' order by _rank) as l_0 '
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
  return substring(callsign from '[\d]*[A-Z]+\d+[A-Z]+');
end$$;


ALTER FUNCTION public.strip_callsign(callsign character varying) OWNER TO postgres;

--
-- Name: tf_activators_bi(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION tf_activators_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  new.activator = strip_callsign(new.activator);
  if new.activator is null
  then
    return null;
  else
    return new;
  end if;
 end$$;


ALTER FUNCTION public.tf_activators_bi() OWNER TO postgres;

--
-- Name: tf_cfm_request_qso_bi(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION tf_cfm_request_qso_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  if exists (select 1 from qso, uploads 
	where upload_id = uploads.id and enabled
	and callsign = new.callsign and rda = new.rda
	and station_callsign = new.station_callsign
	and band = new.band and mode = new.mode 
	and qso.tstamp = new.tstamp) then
    return null;
   end if;
  if exists (select 1 from cfm_request_qso
	where callsign = new.callsign and rda = new.rda
	and station_callsign = new.station_callsign
	and band = new.band and mode = new.mode 
	and tstamp = new.tstamp) then
    return null;
   end if;   
   return new;
 end$$;


ALTER FUNCTION public.tf_cfm_request_qso_bi() OWNER TO postgres;

--
-- Name: tf_qso_bi(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION tf_qso_bi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  new.callsign = strip_callsign(new.callsign);
  new.dt = date(new.tstamp);
  if new.callsign is null
  then
    return null;
  end if;
  if (new.tstamp < '06-12-1991') 
  then
    return null;
  else
    return new;
  end if;
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
    state boolean
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
    correspondent_email character varying(64) NOT NULL
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
    dt date DEFAULT date(now()) NOT NULL
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
    _rank integer
);


ALTER TABLE rankings OWNER TO postgres;

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
    upload_type character varying(32) DEFAULT 'adif'::character varying
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

ALTER TABLE ONLY cfm_qsl_qso ALTER COLUMN id SET DEFAULT nextval('cfm_qsl_qso_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY cfm_request_qso ALTER COLUMN id SET DEFAULT nextval('cfm_request_qso_id_seq'::regclass);


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
-- Name: activators_activator_upload_id_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX activators_activator_upload_id_idx ON activators USING btree (activator, upload_id);


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
-- Name: qso_callsign_band_rda_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_callsign_band_rda_idx ON qso USING btree (callsign, band, rda);


--
-- Name: qso_callsign_mode_band_rda_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_callsign_mode_band_rda_idx ON qso USING btree (callsign, mode, band, rda);


--
-- Name: qso_callsign_mode_rda_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_callsign_mode_rda_idx ON qso USING btree (callsign, mode, rda);


--
-- Name: qso_upload_id_mode_band_rda_callsign_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_upload_id_mode_band_rda_callsign_idx ON qso USING btree (upload_id, mode, band, rda, callsign);


--
-- Name: qso_upload_id_mode_band_rda_dt_callsign_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_upload_id_mode_band_rda_dt_callsign_idx ON qso USING btree (upload_id, mode, band, rda, dt, callsign);


--
-- Name: qso_upload_id_station_callsign_rda_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_upload_id_station_callsign_rda_idx ON qso USING btree (upload_id, station_callsign, rda);


--
-- Name: rankings_callsign_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX rankings_callsign_idx ON rankings USING btree (callsign);


--
-- Name: rankings_top100; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX rankings_top100 ON rankings USING btree (role, mode, band, callsign, _count, _rank) WHERE (_rank < 101);


--
-- Name: uploads_id_enabled_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX uploads_id_enabled_idx ON uploads USING btree (id, enabled);


--
-- Name: uploads_id_user_cs_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX uploads_id_user_cs_idx ON uploads USING btree (id, user_cs);


--
-- Name: uploads_id_user_cs_upload_type_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX uploads_id_user_cs_upload_type_idx ON uploads USING btree (id, user_cs, upload_type);


--
-- Name: uploads_user_cs_id_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX uploads_user_cs_id_idx ON uploads USING btree (user_cs, id);


--
-- Name: uploads_user_cs_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX uploads_user_cs_idx ON uploads USING btree (user_cs);


--
-- Name: tr_activators_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_activators_bi BEFORE INSERT ON activators FOR EACH ROW EXECUTE PROCEDURE tf_activators_bi();


--
-- Name: tr_cfm_requests_qso_bi; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_cfm_requests_qso_bi BEFORE INSERT ON cfm_request_qso FOR EACH ROW EXECUTE PROCEDURE tf_cfm_request_qso_bi();


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
-- Name: qso_upload_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY qso
    ADD CONSTRAINT qso_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES uploads(id);


--
-- Name: public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM postgres;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- Name: tf_activators_bi(); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION tf_activators_bi() FROM PUBLIC;
REVOKE ALL ON FUNCTION tf_activators_bi() FROM postgres;
GRANT ALL ON FUNCTION tf_activators_bi() TO postgres;
GRANT ALL ON FUNCTION tf_activators_bi() TO PUBLIC;
GRANT ALL ON FUNCTION tf_activators_bi() TO "www-group";


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

