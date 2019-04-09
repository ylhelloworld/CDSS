--
-- PostgreSQL database dump
--

-- Dumped from database version 9.3.11
-- Dumped by pg_dump version 9.6.9

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: sim_state_transition; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.sim_state_transition (sim_state_transition_id, pre_state_id, post_state_id, clinical_item_id, time_trigger, description) FROM stdin;
1	14	15	\N	3600	Active bleed uncontrolled
2	15	4	\N	1800	Bled out, coding
3	15	14	65640	\N	Transfuse RBC temporarily restabilizes
4	15	14	61975	\N	Transfuse RBC temporarily restabilizes
5	14	14	65640	\N	Transfuse RBC temporarily resets state decay
6	14	14	61975	\N	Transfuse RBC temporarily resets state decay timer
7	14	14	43996	\N	Octreotide temporarily stalls variceal bleed
8	14	16	61993	\N	Coagulopathy corrected with FFP
9	14	16	65702	\N	Coagulopathy corrected with FFP
10	14	16	44001	\N	Cogulopathy stabilized with Vitamin K
11	16	2	49481	\N	GI Consult takes patient for EGD
12	16	2	45969	\N	EGD Ordered and Done
15	15	17	49481	\N	GI Consult Block
20	15	17	45969	\N	EGD Block until stabilize
21	14	17	49481	\N	GI Consult block
22	14	17	45969	\N	EGD Block until stabilize
23	17	15	\N	0	Consult block immediately to bleeding out state
24	15	14	45748	\N	Transfuse RBC temporarily restabilizes
25	14	14	45748	\N	Transfuse RBC temporarily resets state decay timer
26	21	18	35850	\N	Insulin given for DKA, normalizes glucose
27	18	20	\N	3600	Only insulin given, DKA patient becomes hypoglycemic
28	20	18	44201	\N	Glucose and or potassium added back?
30	20	18	44239	\N	Glucose and or potassium added back?
31	20	18	44316	\N	Glucose and or potassium added back?
32	20	18	46277	\N	Glucose and or potassium added back?
33	20	18	46505	\N	Glucose and or potassium added back?
29	18	19	44201	\N	Gap closed when ongoing insulin supplemented by glucose and potassium
34	18	19	44239	\N	Gap closed when ongoing insulin supplemented by glucose and potassium
35	18	19	44316	\N	Gap closed when ongoing insulin supplemented by glucose and potassium
36	18	19	46277	\N	Gap closed when ongoing insulin supplemented by glucose and potassium
37	18	19	46505	\N	Gap closed when ongoing insulin supplemented by glucose and potassium
5000	5000	5001	44391	\N	Appropriate antibiotics improve patient condition - Zosyn (pip/tazo)
5010	5000	5001	44252	\N	Appropriate antibiotics improve patient condition - Zosyn (pip/tazo) (alternate)
5020	5000	5001	44008	\N	Appropriate antibiotics improve patient condition - Meropenem
5030	5000	5001	36210	\N	Appropriate antibiotics improve patient condition - Cefepime
5040	5000	5001	44678	\N	Appropriate antibiotics improve patient condition - Aztreonam
5050	5000	5001	44637	\N	Appropriate antibiotics improve patient condition - Ceftazadime
5100	5000	5002	44198	\N	IV Fluid resuscitation improves patient condition - Sodium Chloride/Normal Saline
5110	5000	5002	44439	\N	IV Fluid resuscitation improves patient condition - Lactated Ringers
5120	5000	5002	44290	\N	IV Fluid resuscitation improves patient condition - Lactated Ringers v2
5210	5001	5003	44198	\N	IV Fluid resuscitation improves patient condition - Sodium Chloride/Normal Saline
5220	5001	5003	44439	\N	IV Fluid resuscitation improves patient condition - Lactated Ringers
5230	5001	5003	44290	\N	IV Fluid resuscitation improves patient condition - Lactated Ringers v2
5300	5002	5003	44391	\N	Appropriate antibiotics improve patient condition - Zosyn (pip/tazo)
5310	5002	5003	44252	\N	Appropriate antibiotics improve patient condition - Zosyn (pip/tazo) (alternate)
5320	5002	5003	44008	\N	Appropriate antibiotics improve patient condition - Meropenem
5330	5002	5003	36210	\N	Appropriate antibiotics improve patient condition - Cefepime
5340	5002	5003	44678	\N	Appropriate antibiotics improve patient condition - Aztreonam
5350	5002	5003	44637	\N	Appropriate antibiotics improve patient condition - Ceftazadime
\.


--
-- Name: sim_state_transition_sim_state_transition_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.sim_state_transition_sim_state_transition_id_seq', 37, true);


--
-- PostgreSQL database dump complete
--

