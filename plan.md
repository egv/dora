# Dora the Explora

## Intro

Dora is autonomous AI agent that does the following: it receives city name as input, and then it searches for events in that given city that are taking place in the following two weeks. For each of the events we try to estimate its size (nu,ber of potential visitors), its importance (how important is this event for the given city) and 3 basic auditories (for ex. males 35-40, hight income, single). Next, we generate push notification texts for eaxh of the auditories. Text should offer the user to take a taxi ride to the event with a 10% discount. Each text should be done in languages, that are spoken in the city.

Results should be presented in a structured way.

## Architecture

Each task should be processed by a specific agent, that is proficent in this exact task. There should be orchestration agent, that passes messages between other agents ad coordinate work in any other required way.

All communicaiton between agents should be done using strongly types and structured data

## Agents descriptions

### Orchestration agent

it takes city name as input, then it runs all other agents to achieve required result

### Event finder agent

uses perplexity api to select events in the given city

### Event classifier agent

classifies the given event. Finds user audiences.

### Language selector agent

returns number of languages that are spoken in the given city

### Text writer agent

this agents revieves descrition of event, description of user group and language, and return push notification text


