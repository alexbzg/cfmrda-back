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
-- Name: uploads; Type: TABLE; Schema: public; Owner: postgres; Tablespace: 
--

CREATE TABLE uploads (
    id integer NOT NULL,
    "user" character varying(32) NOT NULL,
    tstamp timestamp without time zone DEFAULT now() NOT NULL,
    rda character(5) NOT NULL,
    station_callsign character varying(32) NOT NULL,
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
-- Name: qso_upload_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY qso
    ADD CONSTRAINT qso_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES uploads(id);


--
-- Name: uploads_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY uploads
    ADD CONSTRAINT uploads_user_fkey FOREIGN KEY ("user") REFERENCES users(callsign);


--
-- Name: public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM postgres;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO PUBLIC;


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

