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
-- Name: add_qso(character varying, character varying, character, character varying); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION add_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) RETURNS void
    LANGUAGE plpgsql
    AS $$declare
  _activator_callsign character varying; 
begin
  _activator_callsign := get_activator_callsign(_station_callsign);
  if exists(select from stats_activators 
    where callsign = _activator_callsign and
      rda = _rda and band = _band)
  then
    update stats_activators set qso_count = qso_count + 1
      where callsign = _activator_callsign and
        rda = _rda and band = _band;
  else
    insert into stats_activators 
      values (_activator_callsign, _rda, _band, 1);
  end if;
  if not exists(select from stats_hunters 
    where callsign = _callsign and rda = _rda and
      band = _band)
  then
    insert into stats_hunters
      values(_callsign, _rda, _band);
  end if;
end
    
	$$;


ALTER FUNCTION public.add_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) OWNER TO postgres;

--
-- Name: get_activator_callsign(character varying); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION get_activator_callsign(callsign character varying) RETURNS character
    LANGUAGE plpgsql
    AS $$begin
  return substring(callsign from '[A-Z]+\d+[A-Z]+');
end
  $$;


ALTER FUNCTION public.get_activator_callsign(callsign character varying) OWNER TO postgres;

--
-- Name: recreate_stats(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION recreate_stats() RETURNS void
    LANGUAGE plpgsql
    AS $$begin
  delete from stats_hunters;
  delete from stats_activators;
  insert into stats_hunters select distinct callsign, rda, band from qso;
  insert into stats_activators 
     select get_activator_callsign(station_callsign), rda, band, sum(1) from qso
       group by get_activator_callsign(station_callsign), rda, band;
end$$;


ALTER FUNCTION public.recreate_stats() OWNER TO postgres;

--
-- Name: remove_qso(character varying, character varying, character, character varying); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION remove_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) RETURNS void
    LANGUAGE plpgsql
    AS $$declare
  _activator_callsign character varying; 
begin
  _activator_callsign := get_activator_callsign(_station_callsign);
  update stats_activators set qso_count = qso_count - 1
    where callsign = _activator_callsign and 
      rda = _rda and band = _band;
  if not exists(select from qso 
    where callsign = _callsign and rda = _rda and band = _band)
  then
    delete from stats_hunters 
      where callsign = _callsign and rda = _rda and band = _band;
  end if;
end
	$$;


ALTER FUNCTION public.remove_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) OWNER TO postgres;

--
-- Name: tf_qso_ad(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION tf_qso_ad() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  perform remove_qso(old.callsign, old.station_callsign,
    old.rda, old.band);
  return old;
end$$;


ALTER FUNCTION public.tf_qso_ad() OWNER TO postgres;

--
-- Name: tf_qso_ai(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION tf_qso_ai() RETURNS trigger
    LANGUAGE plpgsql
    AS $$begin
  perform add_qso(new.callsign, new.station_callsign,
    new.rda, new.band);
  return new;
end
$$;


ALTER FUNCTION public.tf_qso_ai() OWNER TO postgres;

SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: qso; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE qso (
    id integer NOT NULL,
    upload_id integer NOT NULL,
    callsign character varying(32) NOT NULL,
    station_callsign character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(8) NOT NULL,
    mode character varying(16) NOT NULL,
    tstamp timestamp without time zone NOT NULL
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
-- Name: stats_activators; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE stats_activators (
    callsign character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(16) NOT NULL,
    qso_count integer DEFAULT 0 NOT NULL
);


ALTER TABLE stats_activators OWNER TO postgres;

--
-- Name: stats_hunters; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE stats_hunters (
    callsign character varying(32) NOT NULL,
    rda character(5) NOT NULL,
    band character varying(16) NOT NULL
);


ALTER TABLE stats_hunters OWNER TO postgres;

--
-- Name: uploads; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE uploads (
    id integer NOT NULL,
    user_cs character varying(32) NOT NULL,
    tstamp timestamp without time zone DEFAULT now() NOT NULL,
    rda character(5) NOT NULL,
    date_start date NOT NULL,
    date_end date NOT NULL
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

ALTER TABLE ONLY qso ALTER COLUMN id SET DEFAULT nextval('qso_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY uploads ALTER COLUMN id SET DEFAULT nextval('uploads_id_seq'::regclass);


--
-- Name: qso_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY qso
    ADD CONSTRAINT qso_pkey PRIMARY KEY (id);


--
-- Name: stats_activators_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY stats_activators
    ADD CONSTRAINT stats_activators_pkey PRIMARY KEY (callsign, rda, band);


--
-- Name: stats_hunters_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres; Tablespace: 
--

ALTER TABLE ONLY stats_hunters
    ADD CONSTRAINT stats_hunters_pkey PRIMARY KEY (callsign, rda, band);


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
-- Name: qso_callsign_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_callsign_idx ON qso USING btree (callsign);


--
-- Name: qso_rda_band_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_rda_band_idx ON qso USING btree (rda, band);


--
-- Name: qso_upload_id_idx; Type: INDEX; Schema: public; Owner: postgres; Tablespace: 
--

CREATE INDEX qso_upload_id_idx ON qso USING btree (upload_id);


--
-- Name: tr_qso_ad; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_qso_ad AFTER DELETE ON qso FOR EACH ROW EXECUTE PROCEDURE tf_qso_ad();


--
-- Name: tr_qso_ai; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER tr_qso_ai AFTER INSERT ON qso FOR EACH ROW EXECUTE PROCEDURE tf_qso_ai();


--
-- Name: qso_upload_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY qso
    ADD CONSTRAINT qso_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES uploads(id);


--
-- Name: uploads_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY uploads
    ADD CONSTRAINT uploads_user_fkey FOREIGN KEY (user_cs) REFERENCES users(callsign);


--
-- Name: public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM postgres;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- Name: add_qso(character varying, character varying, character, character varying); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION add_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) FROM PUBLIC;
REVOKE ALL ON FUNCTION add_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) FROM postgres;
GRANT ALL ON FUNCTION add_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) TO postgres;
GRANT ALL ON FUNCTION add_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) TO PUBLIC;
GRANT ALL ON FUNCTION add_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) TO "www-group";


--
-- Name: remove_qso(character varying, character varying, character, character varying); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION remove_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) FROM PUBLIC;
REVOKE ALL ON FUNCTION remove_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) FROM postgres;
GRANT ALL ON FUNCTION remove_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) TO postgres;
GRANT ALL ON FUNCTION remove_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) TO PUBLIC;
GRANT ALL ON FUNCTION remove_qso(_callsign character varying, _station_callsign character varying, _rda character, _band character varying) TO "www-group";


--
-- Name: tf_qso_ad(); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION tf_qso_ad() FROM PUBLIC;
REVOKE ALL ON FUNCTION tf_qso_ad() FROM postgres;
GRANT ALL ON FUNCTION tf_qso_ad() TO postgres;
GRANT ALL ON FUNCTION tf_qso_ad() TO PUBLIC;
GRANT ALL ON FUNCTION tf_qso_ad() TO "www-group";


--
-- Name: tf_qso_ai(); Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON FUNCTION tf_qso_ai() FROM PUBLIC;
REVOKE ALL ON FUNCTION tf_qso_ai() FROM postgres;
GRANT ALL ON FUNCTION tf_qso_ai() TO postgres;
GRANT ALL ON FUNCTION tf_qso_ai() TO PUBLIC;
GRANT ALL ON FUNCTION tf_qso_ai() TO "www-group";


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
-- Name: stats_activators; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE stats_activators FROM PUBLIC;
REVOKE ALL ON TABLE stats_activators FROM postgres;
GRANT ALL ON TABLE stats_activators TO postgres;
GRANT SELECT,INSERT,DELETE,TRIGGER,UPDATE ON TABLE stats_activators TO "www-group";


--
-- Name: stats_hunters; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE stats_hunters FROM PUBLIC;
REVOKE ALL ON TABLE stats_hunters FROM postgres;
GRANT ALL ON TABLE stats_hunters TO postgres;
GRANT SELECT,INSERT,DELETE,TRIGGER,UPDATE ON TABLE stats_hunters TO "www-group";


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

