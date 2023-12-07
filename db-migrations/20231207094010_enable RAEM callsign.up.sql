CREATE OR REPLACE FUNCTION public.strip_callsign(
	callsign character varying)
    RETURNS character varying
    LANGUAGE 'plpgsql'
    COST 100
    IMMUTABLE PARALLEL UNSAFE
AS $BODY$
begin
  if substring(callsign from '[^\dA-Z/]') is not null then
    return null;
  end if;
  return substring(callsign from '([\d]*[A-Z]+\d+[A-Z]+|RAEM)');
end
$BODY$;

ALTER FUNCTION public.strip_callsign(character varying)
    OWNER TO postgres;

