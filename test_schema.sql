--
-- PostgreSQL database dump
--

\restrict RJaegzovZKQbawllK6Gj4p6FSrwyxNEIdYfoxJLZQ1h9o0Arg62BzRKJ1ocv3Oo

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: test; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA test;


--
-- Name: trim_alarm_value(); Type: FUNCTION; Schema: test; Owner: -
--

CREATE FUNCTION test.trim_alarm_value() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE
            v_count bigint;
            v_keep  integer := 2000;  -- 유지할 최대 건수
        BEGIN
            -- 현재 전체 건수 조회
            SELECT count(*) INTO v_count FROM "ALARM_VALUE";

            IF v_count >= v_keep THEN
                -- 오래된 것부터 (TIMESTAMP, TAG_ID 기준) 남길 개수만 제외하고 삭제
                DELETE FROM "ALARM_VALUE"
                WHERE ("TIMESTAMP", "TAG_ID") IN (
                    SELECT "TIMESTAMP", "TAG_ID"
                    FROM "ALARM_VALUE"
                    ORDER BY "TIMESTAMP" ASC, "TAG_ID" ASC
                    LIMIT v_count - (v_keep - 1)
                );
            END IF;

            -- STATEMENT 트리거라 RETURN NULL
            RETURN NULL;
        END;
        $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ALARM_HIST; Type: TABLE; Schema: test; Owner: -
--

CREATE TABLE test."ALARM_HIST" (
    "TIMESTAMP" timestamp(3) with time zone NOT NULL,
    "TAG_ID" integer NOT NULL,
    "TAG_NAME" character varying(40) NOT NULL,
    "DESCRIPTION" character varying(72),
    "PRIORITY" smallint NOT NULL,
    "VALUE" double precision NOT NULL,
    "IS_ALM" smallint NOT NULL,
    "MESSAGE" character varying(50) NOT NULL
);


--
-- Name: TABLE "ALARM_HIST"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON TABLE test."ALARM_HIST" IS '알람 이력 로그';


--
-- Name: COLUMN "ALARM_HIST"."TIMESTAMP"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_HIST"."TIMESTAMP" IS '시각';


--
-- Name: COLUMN "ALARM_HIST"."TAG_ID"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_HIST"."TAG_ID" IS '태그 ID';


--
-- Name: COLUMN "ALARM_HIST"."TAG_NAME"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_HIST"."TAG_NAME" IS '태그 이름';


--
-- Name: COLUMN "ALARM_HIST"."DESCRIPTION"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_HIST"."DESCRIPTION" IS '설명';


--
-- Name: COLUMN "ALARM_HIST"."PRIORITY"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_HIST"."PRIORITY" IS '알람 우선순위';


--
-- Name: COLUMN "ALARM_HIST"."VALUE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_HIST"."VALUE" IS '측정값';


--
-- Name: COLUMN "ALARM_HIST"."IS_ALM"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_HIST"."IS_ALM" IS '알람 활성 여부';


--
-- Name: COLUMN "ALARM_HIST"."MESSAGE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_HIST"."MESSAGE" IS '알람 메시지';


--
-- Name: ALARM_VALUE; Type: TABLE; Schema: test; Owner: -
--

CREATE UNLOGGED TABLE test."ALARM_VALUE" (
    "TIMESTAMP" timestamp(3) with time zone NOT NULL,
    "TAG_ID" integer NOT NULL,
    "TAG_NAME" character varying(40) NOT NULL,
    "DESCRIPTION" character varying(72),
    "PRIORITY" smallint NOT NULL,
    "VALUE" double precision NOT NULL,
    "IS_ALM" smallint NOT NULL,
    "MESSAGE" character varying(50) NOT NULL,
    "IS_ACK" smallint DEFAULT 0 NOT NULL,
    "ACK_TIME" timestamp(3) with time zone
);


--
-- Name: TABLE "ALARM_VALUE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON TABLE test."ALARM_VALUE" IS '최근 알람 이벤트 로그';


--
-- Name: COLUMN "ALARM_VALUE"."TIMESTAMP"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_VALUE"."TIMESTAMP" IS '시각';


--
-- Name: COLUMN "ALARM_VALUE"."TAG_ID"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_VALUE"."TAG_ID" IS '태그 ID';


--
-- Name: COLUMN "ALARM_VALUE"."TAG_NAME"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_VALUE"."TAG_NAME" IS '태그 이름';


--
-- Name: COLUMN "ALARM_VALUE"."DESCRIPTION"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_VALUE"."DESCRIPTION" IS '설명';


--
-- Name: COLUMN "ALARM_VALUE"."PRIORITY"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_VALUE"."PRIORITY" IS '알람 우선순위';


--
-- Name: COLUMN "ALARM_VALUE"."VALUE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_VALUE"."VALUE" IS '측정값';


--
-- Name: COLUMN "ALARM_VALUE"."IS_ALM"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_VALUE"."IS_ALM" IS '알람 활성 여부';


--
-- Name: COLUMN "ALARM_VALUE"."MESSAGE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_VALUE"."MESSAGE" IS '메시지 내용';


--
-- Name: COLUMN "ALARM_VALUE"."IS_ACK"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_VALUE"."IS_ACK" IS '확인(ACK) 여부';


--
-- Name: COLUMN "ALARM_VALUE"."ACK_TIME"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."ALARM_VALUE"."ACK_TIME" IS '확인 시각';


--
-- Name: MIMIC_FILE; Type: TABLE; Schema: test; Owner: -
--

CREATE TABLE test."MIMIC_FILE" (
    "FILE_PATH" character varying(500) NOT NULL,
    "FILE_SIZE" bigint DEFAULT 0 NOT NULL,
    "LAST_WRITE_TICKS" bigint DEFAULT 0 NOT NULL,
    "CHG_DATE" timestamp with time zone DEFAULT now() NOT NULL,
    "CHG_ID" character varying(30) DEFAULT ''::character varying NOT NULL
);


--
-- Name: COLUMN "MIMIC_FILE"."FILE_PATH"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."MIMIC_FILE"."FILE_PATH" IS '파일경로';


--
-- Name: COLUMN "MIMIC_FILE"."FILE_SIZE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."MIMIC_FILE"."FILE_SIZE" IS '파일크기';


--
-- Name: COLUMN "MIMIC_FILE"."CHG_DATE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."MIMIC_FILE"."CHG_DATE" IS '수정일자';


--
-- Name: COLUMN "MIMIC_FILE"."CHG_ID"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."MIMIC_FILE"."CHG_ID" IS '수정자ID';


--
-- Name: MIMIC_FILE_TAG; Type: TABLE; Schema: test; Owner: -
--

CREATE TABLE test."MIMIC_FILE_TAG" (
    "FILE_PATH" character varying(500) NOT NULL,
    "TAG_NAME" character varying(100) NOT NULL
);


--
-- Name: COLUMN "MIMIC_FILE_TAG"."FILE_PATH"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."MIMIC_FILE_TAG"."FILE_PATH" IS '파일경로';


--
-- Name: COLUMN "MIMIC_FILE_TAG"."TAG_NAME"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."MIMIC_FILE_TAG"."TAG_NAME" IS '태그명';


--
-- Name: TAG_INFO; Type: TABLE; Schema: test; Owner: -
--

CREATE TABLE test."TAG_INFO" (
    "TAG_NAME" character varying(70) NOT NULL,
    "DESCRIPTION" character varying(128),
    "SIG_TYPE" character varying(5),
    "TAG_ID" integer NOT NULL,
    "SENS_TAG" character varying(70),
    "SYSTEM" character varying(10) NOT NULL,
    "SCAN" character(1) DEFAULT 'N'::bpchar,
    "FORCE" character(1) DEFAULT 'N'::bpchar,
    "INIT_VAL" double precision,
    "L_SENVAL" double precision DEFAULT 0,
    "H_SENVAL" double precision DEFAULT 100,
    "SEN_UNIT" character varying(20),
    "L_ENGVAL" double precision DEFAULT 0,
    "H_ENGVAL" double precision DEFAULT 100,
    "ENG_UNIT" character varying(20),
    "EU_CONV" character(1) DEFAULT 'N'::bpchar,
    "CONV_TYPE" character varying(3),
    "X0_COEFF" double precision DEFAULT 0,
    "X1_COEFF" double precision DEFAULT 0,
    "X2_COEFF" double precision DEFAULT 0,
    "X3_COEFF" double precision DEFAULT 0,
    "X4_COEFF" double precision DEFAULT 0,
    "X5_COEFF" double precision DEFAULT 0,
    "DEC_POINT" smallint,
    "L_INVVAL" double precision DEFAULT 0,
    "H_INVVAL" double precision DEFAULT 0,
    "ALARM" character(1) DEFAULT 'N'::bpchar,
    "ALM_DELAY" double precision DEFAULT 0,
    "LL_ALM_VAL" double precision DEFAULT 0,
    "LO_ALM_VAL" double precision DEFAULT 0,
    "HI_ALM_VAL" double precision DEFAULT 0,
    "HH_ALM_VAL" double precision DEFAULT 0,
    "LL_ALM_PRIO" smallint DEFAULT 0,
    "LO_ALM_PRIO" smallint DEFAULT 0,
    "HI_ALM_PRIO" smallint DEFAULT 0,
    "HH_ALM_PRIO" smallint DEFAULT 0,
    "D_ALM_PRIO1" smallint DEFAULT 0,
    "D_ALM_PRIO2" smallint DEFAULT 0,
    "ALM_CND" smallint DEFAULT 1,
    "CLSD_MSG" character varying(20),
    "OPEN_MSG" character varying(20),
    "DEADBAND_MODE" smallint DEFAULT 0 NOT NULL,
    "DEADBAND" double precision DEFAULT 0,
    "DEADBAND_MIN_ABS" double precision DEFAULT 0,
    "COM_ID" character varying(10),
    "NODE_NO" smallint DEFAULT 0,
    "CHASS_NO" smallint DEFAULT 0,
    "CARD_SLT" smallint DEFAULT 0,
    "CH_NO" smallint DEFAULT 0,
    "COMM_REF_NO" smallint DEFAULT 0,
    "DATA_ADR" character varying(24),
    "DATA_SRC" character varying(10),
    "DIA_NO" character varying(20),
    "DOC_NO" character varying(100),
    "NOTE1" character varying(100),
    "NOTE2" character varying(100),
    "DATA_TYPE" character(2),
    "DEVICE_ID" smallint DEFAULT 0,
    "USED" character(1) DEFAULT 'Y'::bpchar
);


--
-- Name: TABLE "TAG_INFO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON TABLE test."TAG_INFO" IS '태그 마스터 설정';


--
-- Name: COLUMN "TAG_INFO"."TAG_NAME"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."TAG_NAME" IS '태그 이름';


--
-- Name: COLUMN "TAG_INFO"."DESCRIPTION"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DESCRIPTION" IS '설명';


--
-- Name: COLUMN "TAG_INFO"."SIG_TYPE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."SIG_TYPE" IS '신호 타입';


--
-- Name: COLUMN "TAG_INFO"."TAG_ID"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."TAG_ID" IS '태그 ID';


--
-- Name: COLUMN "TAG_INFO"."SENS_TAG"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."SENS_TAG" IS '원본 센서 태그';


--
-- Name: COLUMN "TAG_INFO"."SYSTEM"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."SYSTEM" IS '시스템 코드';


--
-- Name: COLUMN "TAG_INFO"."SCAN"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."SCAN" IS '스캔 사용 여부';


--
-- Name: COLUMN "TAG_INFO"."FORCE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."FORCE" IS '강제 모드 여부';


--
-- Name: COLUMN "TAG_INFO"."INIT_VAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."INIT_VAL" IS '초기값';


--
-- Name: COLUMN "TAG_INFO"."L_SENVAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."L_SENVAL" IS '센서 하한 범위';


--
-- Name: COLUMN "TAG_INFO"."H_SENVAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."H_SENVAL" IS '센서 상한 범위';


--
-- Name: COLUMN "TAG_INFO"."SEN_UNIT"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."SEN_UNIT" IS '센서 단위';


--
-- Name: COLUMN "TAG_INFO"."L_ENGVAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."L_ENGVAL" IS '공학 하한 범위';


--
-- Name: COLUMN "TAG_INFO"."H_ENGVAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."H_ENGVAL" IS '공학 상한 범위';


--
-- Name: COLUMN "TAG_INFO"."ENG_UNIT"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."ENG_UNIT" IS '공학 단위';


--
-- Name: COLUMN "TAG_INFO"."EU_CONV"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."EU_CONV" IS '공학 단위 변환 여부';


--
-- Name: COLUMN "TAG_INFO"."CONV_TYPE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."CONV_TYPE" IS '변환 타입';


--
-- Name: COLUMN "TAG_INFO"."X0_COEFF"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."X0_COEFF" IS '변환 계수 X0';


--
-- Name: COLUMN "TAG_INFO"."X1_COEFF"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."X1_COEFF" IS '변환 계수 X1';


--
-- Name: COLUMN "TAG_INFO"."X2_COEFF"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."X2_COEFF" IS '변환 계수 X2';


--
-- Name: COLUMN "TAG_INFO"."X3_COEFF"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."X3_COEFF" IS '변환 계수 X3';


--
-- Name: COLUMN "TAG_INFO"."X4_COEFF"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."X4_COEFF" IS '변환 계수 X4';


--
-- Name: COLUMN "TAG_INFO"."X5_COEFF"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."X5_COEFF" IS '변환 계수 X5';


--
-- Name: COLUMN "TAG_INFO"."DEC_POINT"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DEC_POINT" IS '소수점 자리수';


--
-- Name: COLUMN "TAG_INFO"."L_INVVAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."L_INVVAL" IS '유효 하한값';


--
-- Name: COLUMN "TAG_INFO"."H_INVVAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."H_INVVAL" IS '유효 상한값';


--
-- Name: COLUMN "TAG_INFO"."ALARM"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."ALARM" IS '알람 사용 여부';


--
-- Name: COLUMN "TAG_INFO"."ALM_DELAY"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."ALM_DELAY" IS '알람 지연 시간(초)';


--
-- Name: COLUMN "TAG_INFO"."LL_ALM_VAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."LL_ALM_VAL" IS 'LL 알람 기준값';


--
-- Name: COLUMN "TAG_INFO"."LO_ALM_VAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."LO_ALM_VAL" IS 'LO 알람 기준값';


--
-- Name: COLUMN "TAG_INFO"."HI_ALM_VAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."HI_ALM_VAL" IS 'HI 알람 기준값';


--
-- Name: COLUMN "TAG_INFO"."HH_ALM_VAL"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."HH_ALM_VAL" IS 'HH 알람 기준값';


--
-- Name: COLUMN "TAG_INFO"."LL_ALM_PRIO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."LL_ALM_PRIO" IS 'LL 알람 우선순위';


--
-- Name: COLUMN "TAG_INFO"."LO_ALM_PRIO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."LO_ALM_PRIO" IS 'LO 알람 우선순위';


--
-- Name: COLUMN "TAG_INFO"."HI_ALM_PRIO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."HI_ALM_PRIO" IS 'HI 알람 우선순위';


--
-- Name: COLUMN "TAG_INFO"."HH_ALM_PRIO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."HH_ALM_PRIO" IS 'HH 알람 우선순위';


--
-- Name: COLUMN "TAG_INFO"."D_ALM_PRIO1"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."D_ALM_PRIO1" IS '디지털 알람 우선순위 1';


--
-- Name: COLUMN "TAG_INFO"."D_ALM_PRIO2"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."D_ALM_PRIO2" IS '디지털 알람 우선순위 2';


--
-- Name: COLUMN "TAG_INFO"."ALM_CND"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."ALM_CND" IS '알람 조건 타입';


--
-- Name: COLUMN "TAG_INFO"."CLSD_MSG"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."CLSD_MSG" IS '닫힘 상태 메시지';


--
-- Name: COLUMN "TAG_INFO"."OPEN_MSG"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."OPEN_MSG" IS '열림 상태 메시지';


--
-- Name: COLUMN "TAG_INFO"."DEADBAND_MODE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DEADBAND_MODE" IS '데드밴드 모드';


--
-- Name: COLUMN "TAG_INFO"."DEADBAND"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DEADBAND" IS '데드밴드 값';


--
-- Name: COLUMN "TAG_INFO"."DEADBAND_MIN_ABS"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DEADBAND_MIN_ABS" IS '데드밴드 최소 절대값';


--
-- Name: COLUMN "TAG_INFO"."COM_ID"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."COM_ID" IS '통신 인터페이스 ID';


--
-- Name: COLUMN "TAG_INFO"."NODE_NO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."NODE_NO" IS '노드 번호';


--
-- Name: COLUMN "TAG_INFO"."CHASS_NO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."CHASS_NO" IS '섀시 번호';


--
-- Name: COLUMN "TAG_INFO"."CARD_SLT"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."CARD_SLT" IS '카드 슬롯 번호';


--
-- Name: COLUMN "TAG_INFO"."CH_NO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."CH_NO" IS '채널 번호';


--
-- Name: COLUMN "TAG_INFO"."COMM_REF_NO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."COMM_REF_NO" IS '통신 참조 번호';


--
-- Name: COLUMN "TAG_INFO"."DATA_ADR"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DATA_ADR" IS '데이터 주소';


--
-- Name: COLUMN "TAG_INFO"."DATA_SRC"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DATA_SRC" IS '데이터 소스';


--
-- Name: COLUMN "TAG_INFO"."DIA_NO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DIA_NO" IS '계기 번호';


--
-- Name: COLUMN "TAG_INFO"."DOC_NO"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DOC_NO" IS '문서 번호';


--
-- Name: COLUMN "TAG_INFO"."NOTE1"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."NOTE1" IS '비고 1';


--
-- Name: COLUMN "TAG_INFO"."NOTE2"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."NOTE2" IS '비고 2';


--
-- Name: COLUMN "TAG_INFO"."DATA_TYPE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DATA_TYPE" IS '데이터 타입 코드';


--
-- Name: COLUMN "TAG_INFO"."DEVICE_ID"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."DEVICE_ID" IS '장치 ID';


--
-- Name: COLUMN "TAG_INFO"."USED"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO"."USED" IS '사용 여부';


--
-- Name: TAG_INFO_EXT; Type: TABLE; Schema: test; Owner: -
--

CREATE TABLE test."TAG_INFO_EXT" (
    "TAG_ID" integer NOT NULL,
    "TAG_TYPE_CODE" character varying(30) DEFAULT ''::character varying NOT NULL,
    "DISPLAY_NAME" character varying(30) DEFAULT ''::character varying NOT NULL,
    "ENRL_DATE" timestamp with time zone DEFAULT now() NOT NULL,
    "ENRL_ID" character varying(30) DEFAULT ''::character varying NOT NULL,
    "CHG_DATE" timestamp with time zone DEFAULT now() NOT NULL,
    "CHG_ID" character varying(30) DEFAULT ''::character varying NOT NULL
);


--
-- Name: COLUMN "TAG_INFO_EXT"."TAG_ID"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO_EXT"."TAG_ID" IS '태그ID';


--
-- Name: COLUMN "TAG_INFO_EXT"."TAG_TYPE_CODE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO_EXT"."TAG_TYPE_CODE" IS '태그유형';


--
-- Name: COLUMN "TAG_INFO_EXT"."DISPLAY_NAME"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO_EXT"."DISPLAY_NAME" IS '표시명';


--
-- Name: COLUMN "TAG_INFO_EXT"."ENRL_DATE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO_EXT"."ENRL_DATE" IS '등록일시';


--
-- Name: COLUMN "TAG_INFO_EXT"."ENRL_ID"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO_EXT"."ENRL_ID" IS '등록자 ID';


--
-- Name: COLUMN "TAG_INFO_EXT"."CHG_DATE"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO_EXT"."CHG_DATE" IS '수정일시';


--
-- Name: COLUMN "TAG_INFO_EXT"."CHG_ID"; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test."TAG_INFO_EXT"."CHG_ID" IS '수정자 ID';


--
-- Name: asset; Type: TABLE; Schema: test; Owner: -
--

CREATE TABLE test.asset (
    id integer NOT NULL,
    parent_id integer,
    code character varying(50),
    name character varying(200),
    asset_type character varying(100),
    manufacturer character varying(200),
    model_name character varying(200),
    serial_number character varying(100),
    rated_capacity character varying(100),
    rated_speed character varying(100),
    status character varying(50),
    criticality character varying(50),
    system_name character varying(200),
    location character varying(200),
    owner_dept character varying(100),
    owner_person character varying(50),
    install_date date,
    description text,
    mapped_tag_count integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE asset; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON TABLE test.asset IS '설비(장비) 정보';


--
-- Name: COLUMN asset.id; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.id IS '설비 정수 키';


--
-- Name: COLUMN asset.parent_id; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.parent_id IS '상위 설비 id(계통 계층)';


--
-- Name: COLUMN asset.code; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.code IS '설비 코드';


--
-- Name: COLUMN asset.name; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.name IS '설비명';


--
-- Name: COLUMN asset.asset_type; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.asset_type IS '설비 유형';


--
-- Name: COLUMN asset.manufacturer; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.manufacturer IS '제조사';


--
-- Name: COLUMN asset.model_name; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.model_name IS '모델명';


--
-- Name: COLUMN asset.serial_number; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.serial_number IS '제조번호';


--
-- Name: COLUMN asset.rated_capacity; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.rated_capacity IS '정격 용량';


--
-- Name: COLUMN asset.rated_speed; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.rated_speed IS '정격 속도';


--
-- Name: COLUMN asset.status; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.status IS '운전 상태';


--
-- Name: COLUMN asset.criticality; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.criticality IS '설비 중요도';


--
-- Name: COLUMN asset.system_name; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.system_name IS '계통명';


--
-- Name: COLUMN asset.location; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.location IS '설치 위치';


--
-- Name: COLUMN asset.owner_dept; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.owner_dept IS '관리 부서';


--
-- Name: COLUMN asset.owner_person; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.owner_person IS '관리 담당자';


--
-- Name: COLUMN asset.install_date; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.install_date IS '설치일';


--
-- Name: COLUMN asset.description; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.description IS '설비 설명';


--
-- Name: COLUMN asset.mapped_tag_count; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.mapped_tag_count IS '이 설비에 매핑된 태그 수';


--
-- Name: COLUMN asset.created_at; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.created_at IS '최초 적재 시각';


--
-- Name: COLUMN asset.updated_at; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset.updated_at IS '최종 수정 시각';


--
-- Name: asset_tag_link; Type: TABLE; Schema: test; Owner: -
--

CREATE TABLE test.asset_tag_link (
    id bigint NOT NULL,
    asset_id integer NOT NULL,
    tag_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE asset_tag_link; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON TABLE test.asset_tag_link IS '태그↔설비 매핑';


--
-- Name: COLUMN asset_tag_link.id; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset_tag_link.id IS '링크 식별자';


--
-- Name: COLUMN asset_tag_link.asset_id; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset_tag_link.asset_id IS '설비 id(asset.id)';


--
-- Name: COLUMN asset_tag_link.tag_id; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset_tag_link.tag_id IS '태그 id(TAG_INFO.TAG_ID)';


--
-- Name: COLUMN asset_tag_link.created_at; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.asset_tag_link.created_at IS '적재 시각';


--
-- Name: asset_tag_link_id_seq; Type: SEQUENCE; Schema: test; Owner: -
--

CREATE SEQUENCE test.asset_tag_link_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: asset_tag_link_id_seq; Type: SEQUENCE OWNED BY; Schema: test; Owner: -
--

ALTER SEQUENCE test.asset_tag_link_id_seq OWNED BY test.asset_tag_link.id;


--
-- Name: maintenance; Type: TABLE; Schema: test; Owner: -
--

CREATE TABLE test.maintenance (
    id bigint NOT NULL,
    work_code character varying(50) NOT NULL,
    asset_id bigint,
    work_name character varying(300) NOT NULL,
    maint_type character varying(20) NOT NULL,
    priority character varying(20) DEFAULT '보통'::character varying NOT NULL,
    worker character varying(100),
    scheduled_at timestamp with time zone,
    duration_minutes integer DEFAULT 0 NOT NULL,
    completed_at timestamp with time zone,
    status character varying(20) DEFAULT '예정'::character varying NOT NULL,
    cost character varying(50),
    inspection_result character varying(300),
    next_due_date date,
    confirmer character varying(100),
    work_description text,
    team_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT maintenance_maint_type_check CHECK (((maint_type)::text = ANY ((ARRAY['예방정비'::character varying, '예지정비'::character varying, '사후정비'::character varying, '개선공사'::character varying])::text[]))),
    CONSTRAINT maintenance_priority_check CHECK (((priority)::text = ANY ((ARRAY['긴급'::character varying, '높음'::character varying, '보통'::character varying, '낮음'::character varying])::text[]))),
    CONSTRAINT maintenance_status_check CHECK (((status)::text = ANY ((ARRAY['예정'::character varying, '진행'::character varying, '완료'::character varying, '지연'::character varying, '취소'::character varying])::text[])))
);


--
-- Name: TABLE maintenance; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON TABLE test.maintenance IS '정비 이력';


--
-- Name: COLUMN maintenance.id; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.id IS '정비이력 식별자';


--
-- Name: COLUMN maintenance.work_code; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.work_code IS '작업 코드(고유)';


--
-- Name: COLUMN maintenance.asset_id; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.asset_id IS '대상 설비 id(asset.id)';


--
-- Name: COLUMN maintenance.work_name; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.work_name IS '정비 작업명';


--
-- Name: COLUMN maintenance.maint_type; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.maint_type IS '정비 유형(예방정비/예지정비/사후정비/개선공사)';


--
-- Name: COLUMN maintenance.priority; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.priority IS '우선순위(긴급/높음/보통/낮음)';


--
-- Name: COLUMN maintenance.worker; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.worker IS '작업자';


--
-- Name: COLUMN maintenance.scheduled_at; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.scheduled_at IS '예정 일시';


--
-- Name: COLUMN maintenance.duration_minutes; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.duration_minutes IS '소요 시간(분)';


--
-- Name: COLUMN maintenance.completed_at; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.completed_at IS '완료 일시';


--
-- Name: COLUMN maintenance.status; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.status IS '진행 상태(예정/진행/완료/지연/취소)';


--
-- Name: COLUMN maintenance.cost; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.cost IS '비용';


--
-- Name: COLUMN maintenance.inspection_result; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.inspection_result IS '점검 결과 요약';


--
-- Name: COLUMN maintenance.next_due_date; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.next_due_date IS '차기 예정일';


--
-- Name: COLUMN maintenance.confirmer; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.confirmer IS '확인자';


--
-- Name: COLUMN maintenance.work_description; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.work_description IS '정비 상세 내역';


--
-- Name: COLUMN maintenance.team_note; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.team_note IS '팀 메모';


--
-- Name: COLUMN maintenance.created_at; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.created_at IS '최초 적재 시각';


--
-- Name: COLUMN maintenance.updated_at; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.maintenance.updated_at IS '최종 수정 시각';


--
-- Name: maintenance_id_seq; Type: SEQUENCE; Schema: test; Owner: -
--

CREATE SEQUENCE test.maintenance_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: maintenance_id_seq; Type: SEQUENCE OWNED BY; Schema: test; Owner: -
--

ALTER SEQUENCE test.maintenance_id_seq OWNED BY test.maintenance.id;



--
-- Name: tag_description; Type: TABLE; Schema: test; Owner: -
--

CREATE TABLE test.tag_description (
    tag_id integer NOT NULL,
    tag_name character varying(200) NOT NULL,
    description character varying(500),
    tag_nm character varying(200),
    tag_rmk character varying(200),
    tag_desc character varying(200),
    equipment_description text,
    tag_description text,
    value_change_meaning text,
    key_check_points text,
    action_guidance text,
    failure_guidance text,
    related_tags jsonb,
    content_hash character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE tag_description; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON TABLE test.tag_description IS '태그 설명 지식(태그 1:1). LLM 답변 근거';


--
-- Name: COLUMN tag_description.tag_id; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.tag_id IS '태그 정수 키(TAG_INFO.TAG_ID)';


--
-- Name: COLUMN tag_description.tag_name; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.tag_name IS '태그명';


--
-- Name: COLUMN tag_description.description; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.description IS '태그 표시용 설명';


--
-- Name: COLUMN tag_description.tag_nm; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.tag_nm IS '태그 원래 이름';


--
-- Name: COLUMN tag_description.tag_rmk; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.tag_rmk IS '태그 비고/설비 약칭';


--
-- Name: COLUMN tag_description.tag_desc; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.tag_desc IS '태그 부가 표기(계통 등)';


--
-- Name: COLUMN tag_description.equipment_description; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.equipment_description IS '소속 설비 설명';


--
-- Name: COLUMN tag_description.tag_description; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.tag_description IS '태그가 측정/의미하는 바';


--
-- Name: COLUMN tag_description.value_change_meaning; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.value_change_meaning IS '값 상승/하강의 의미(원인 해석)';


--
-- Name: COLUMN tag_description.key_check_points; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.key_check_points IS '핵심 점검 항목';


--
-- Name: COLUMN tag_description.action_guidance; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.action_guidance IS '권장 조치 방향';


--
-- Name: COLUMN tag_description.failure_guidance; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.failure_guidance IS '장애/트립 대응 지침';


--
-- Name: COLUMN tag_description.related_tags; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.related_tags IS '관련 태그 목록 [{tag_name, description}]';



--
-- Name: COLUMN tag_description.content_hash; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.content_hash IS '내용 해시(변경 감지)';


--
-- Name: COLUMN tag_description.created_at; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.created_at IS '최초 적재 시각';


--
-- Name: COLUMN tag_description.updated_at; Type: COMMENT; Schema: test; Owner: -
--

COMMENT ON COLUMN test.tag_description.updated_at IS '최종 수정 시각';


--
-- Name: asset_tag_link id; Type: DEFAULT; Schema: test; Owner: -
--

ALTER TABLE ONLY test.asset_tag_link ALTER COLUMN id SET DEFAULT nextval('test.asset_tag_link_id_seq'::regclass);


--
-- Name: maintenance id; Type: DEFAULT; Schema: test; Owner: -
--

ALTER TABLE ONLY test.maintenance ALTER COLUMN id SET DEFAULT nextval('test.maintenance_id_seq'::regclass);



--
-- Name: MIMIC_FILE PK_MIMIC_FILE; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test."MIMIC_FILE"
    ADD CONSTRAINT "PK_MIMIC_FILE" PRIMARY KEY ("FILE_PATH");


--
-- Name: MIMIC_FILE_TAG PK_MIMIC_FILE_TAG; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test."MIMIC_FILE_TAG"
    ADD CONSTRAINT "PK_MIMIC_FILE_TAG" PRIMARY KEY ("FILE_PATH", "TAG_NAME");


--
-- Name: TAG_INFO_EXT PK_TAG_INFO_EXT; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test."TAG_INFO_EXT"
    ADD CONSTRAINT "PK_TAG_INFO_EXT" PRIMARY KEY ("TAG_ID");


--
-- Name: TAG_INFO TAG_INFO_pkey; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test."TAG_INFO"
    ADD CONSTRAINT "TAG_INFO_pkey" PRIMARY KEY ("TAG_ID");


--
-- Name: ALARM_VALUE alarm_value_pk; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test."ALARM_VALUE"
    ADD CONSTRAINT alarm_value_pk PRIMARY KEY ("TIMESTAMP", "TAG_ID");


--
-- Name: asset asset_pkey; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test.asset
    ADD CONSTRAINT asset_pkey PRIMARY KEY (id);


--
-- Name: asset_tag_link asset_tag_link_asset_id_tag_id_key; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test.asset_tag_link
    ADD CONSTRAINT asset_tag_link_asset_id_tag_id_key UNIQUE (asset_id, tag_id);


--
-- Name: asset_tag_link asset_tag_link_pkey; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test.asset_tag_link
    ADD CONSTRAINT asset_tag_link_pkey PRIMARY KEY (id);


--
-- Name: maintenance maintenance_pkey; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test.maintenance
    ADD CONSTRAINT maintenance_pkey PRIMARY KEY (id);


--
-- Name: maintenance maintenance_work_code_key; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test.maintenance
    ADD CONSTRAINT maintenance_work_code_key UNIQUE (work_code);



--
-- Name: tag_description tag_description_pkey; Type: CONSTRAINT; Schema: test; Owner: -
--

ALTER TABLE ONLY test.tag_description
    ADD CONSTRAINT tag_description_pkey PRIMARY KEY (tag_id);


--
-- Name: ALARM_HIST_TAG_ID_TIMESTAMP_idx; Type: INDEX; Schema: test; Owner: -
--

CREATE INDEX "ALARM_HIST_TAG_ID_TIMESTAMP_idx" ON test."ALARM_HIST" USING btree ("TAG_ID", "TIMESTAMP" DESC);


--
-- Name: IX_MIMIC_FILE_TAG_TAG; Type: INDEX; Schema: test; Owner: -
--

CREATE INDEX "IX_MIMIC_FILE_TAG_TAG" ON test."MIMIC_FILE_TAG" USING btree ("TAG_NAME");


--
-- Name: idx_asset_parent; Type: INDEX; Schema: test; Owner: -
--

CREATE INDEX idx_asset_parent ON test.asset USING btree (parent_id);


--
-- Name: idx_atl_asset; Type: INDEX; Schema: test; Owner: -
--

CREATE INDEX idx_atl_asset ON test.asset_tag_link USING btree (asset_id);


--
-- Name: idx_atl_tag; Type: INDEX; Schema: test; Owner: -
--

CREATE INDEX idx_atl_tag ON test.asset_tag_link USING btree (tag_id);


--
-- Name: idx_maint_asset; Type: INDEX; Schema: test; Owner: -
--

CREATE INDEX idx_maint_asset ON test.maintenance USING btree (asset_id);



--
-- Name: idx_tagdesc_tagname; Type: INDEX; Schema: test; Owner: -
--

CREATE INDEX idx_tagdesc_tagname ON test.tag_description USING btree (tag_name);


--
-- Name: ALARM_VALUE trigger_alarm_value_trim; Type: TRIGGER; Schema: test; Owner: -
--

CREATE TRIGGER trigger_alarm_value_trim BEFORE INSERT ON test."ALARM_VALUE" FOR EACH STATEMENT EXECUTE FUNCTION test.trim_alarm_value();


--
-- PostgreSQL database dump complete
--

\unrestrict RJaegzovZKQbawllK6Gj4p6FSrwyxNEIdYfoxJLZQ1h9o0Arg62BzRKJ1ocv3Oo

